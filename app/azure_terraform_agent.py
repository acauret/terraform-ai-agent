import os
import streamlit as st
from dotenv import load_dotenv
from rag_engine import TerraformRAGEngine
from openai import AzureOpenAI
from langchain.prompts import ChatPromptTemplate

# Set page config first
st.set_page_config(
    page_title="Azure Terraform Generator",
    page_icon="🌩️",
    layout="wide"
)

# Load environment variables
load_dotenv()

# Create a collapsible section for environment configuration
with st.sidebar.expander("⚙️ Environment", expanded=False):
    col1, col2 = st.columns([5, 1])
    with col1:
        st.caption("Azure OpenAI Configuration")
    with col2:
        refresh_button_style = """
            <style>
            div[data-testid="stButton"] button {
                background: none;
                border: none;
                padding: 0;
                margin-top: -10px;
                color: #666;
                font-size: 0.8em;
            }
            div[data-testid="stButton"] button:hover {
                color: #09f;
            }
            </style>
        """
        st.markdown(refresh_button_style, unsafe_allow_html=True)
        if st.button("⟳", help="Refresh Environment Variables"):
            load_dotenv(override=True)
            st.rerun()
    
    # Check each required variable
    api_key = os.getenv('AZURE_OPENAI_API_KEY')
    endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
    chat_deployment = os.getenv('AZURE_OPENAI_CHAT_DEPLOYMENT_NAME')
    embedding_deployment = os.getenv('AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME')
    
    # Display compact status with modern styling
    status_container = st.container()
    with status_container:
        def show_status(name, value, icon):
            if value:
                st.markdown(f'<div style="padding: 4px; color: #28a745">{icon} {name}: <span style="color: #666">Configured</span></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div style="padding: 4px; color: #dc3545">{icon} {name}: <span style="color: #666">Missing</span></div>', unsafe_allow_html=True)
        
        show_status("API Key", api_key, "🔑")
        show_status("Endpoint", endpoint, "🌐")
        show_status("Chat Model", chat_deployment, "💬")
        show_status("Embedding Model", embedding_deployment, "📚")

class AzureTerraformAgent:
    def __init__(self):
        # Ensure Azure OpenAI configuration is set
        required_vars = [
            'AZURE_OPENAI_API_KEY',
            'AZURE_OPENAI_ENDPOINT',
            'AZURE_OPENAI_CHAT_DEPLOYMENT_NAME'
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            st.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
            
        # Initialize Azure OpenAI client
        self.client = AzureOpenAI(
            api_key=os.getenv('AZURE_OPENAI_API_KEY'),
            api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2023-05-15'),
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
            azure_deployment=os.getenv('AZURE_OPENAI_CHAT_DEPLOYMENT_NAME')
        )
            
        # Initialize RAG engine
        self.template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
        if not os.path.exists(self.template_dir):
            raise FileNotFoundError(f"Template directory not found: {self.template_dir}")
        
        # Get path to the terraform directory for main.tf
        self.terraform_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'terraform')
        self.main_tf_path = os.path.join(self.terraform_dir, 'main.tf')
        if not os.path.exists(self.main_tf_path):
            st.warning(f"Base Terraform configuration not found: {self.main_tf_path}")
        
        self.rag_engine = TerraformRAGEngine(self.template_dir)

    def generate_terraform(self, user_input: str) -> tuple:
        """Generate Terraform configuration using RAG approach.
        Returns a tuple of (terraform_code, tfvars_content)
        """
        # Check for specific resource types
        is_resource_group_request = "resource group" in user_input.lower()
        is_storage_account_request = "storage account" in user_input.lower() or "storage accounts" in user_input.lower()
        is_key_vault_request = "key vault" in user_input.lower() or "keyvault" in user_input.lower()
        
        # For specific resource types, we directly get the tfvars
        if is_resource_group_request:
            # For resource groups, get both the main config and tfvars
            configs = self.rag_engine._generate_resource_group_config(user_input)
            return "# Resource group configuration will be in tfvars file", configs['tfvars']
        elif is_storage_account_request:
            # For storage accounts, get both the main config and tfvars
            configs = self.rag_engine._generate_storage_account_config(user_input)
            return "# Storage account configuration will be in tfvars file", configs['tfvars']
        elif is_key_vault_request:
            # For Key Vaults, get both the main config and tfvars
            configs = self.rag_engine._generate_key_vault_config(user_input)
            return "# Key Vault configuration will be in tfvars file", configs['tfvars']
        else:
            # For other resources, use the standard flow
            terraform_code = self.rag_engine.generate_terraform(user_input)
            tfvars_content = self._extract_variables(terraform_code)
            return terraform_code, tfvars_content
    
    def _extract_variables(self, terraform_code: str) -> str:
        """Extract variables from Terraform code and create a tfvars file."""
        try:
            # Check if this is a resource group config
            is_resource_group = "resource_group_name" in terraform_code and "azurerm_resource_group" in terraform_code
            
            if is_resource_group:
                # Extract the resource group name and location from the terraform code
                import re
                
                # Extract resource group name
                rg_name_match = re.search(r'resource_group_name[^=]*=[^"]*"([^"]+)"', terraform_code)
                rg_name = rg_name_match.group(1) if rg_name_match else "my-project"
                
                # Extract location
                location_match = re.search(r'location[^=]*=[^"]*"([^"]+)"', terraform_code)
                location = location_match.group(1) if location_match else "eastus"
                
                # Use the tfvars format from the template
                return f"""# Name of the resource group
resource_group_name = "{rg_name}"

# Azure region where the resource group will be created
location = "{location}"
"""
            
            # For other resource types, use the LLM to generate tfvars
            system_message = """You are a Terraform expert. Given the Terraform configuration, 
            extract all variable declarations and create a terraform.tfvars file with 
            appropriate example values. Include comments explaining each variable.
            
            Format:
            ```
            # Variable name description
            variable_name = "example value"
            
            # Another variable description
            another_variable = 123
            ```
            
            Only include the tfvars content, nothing else."""
            
            result = self.client.chat.completions.create(
                model=os.getenv('AZURE_OPENAI_CHAT_DEPLOYMENT_NAME'),
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": terraform_code}
                ],
                temperature=0.2
            )
            
            return result.choices[0].message.content
        except Exception as e:
            st.error(f"Error generating tfvars file: {str(e)}")
            return "# Error generating tfvars file\n# Please fill in your variable values manually"
        
    def get_main_tf_content(self) -> str:
        """Get the content of the main.tf file from the terraform directory."""
        try:
            with open(self.main_tf_path, 'r') as f:
                return f.read()
        except Exception as e:
            st.error(f"Error reading main.tf: {str(e)}")
            return "# Error loading main.tf template"

# Streamlit UI Component
def azure_terraform_chat():
    st.title("Azure Terraform Generator")
    st.markdown("""
    This tool helps you generate Terraform configurations for Azure infrastructure using AI.
    Simply describe your infrastructure needs, and the AI will generate the appropriate Terraform code.
    
    **Supported Resources:**
    - Resource Groups
    - Virtual Machines
    - AKS (Azure Kubernetes Service)
    - Storage Accounts
    - Virtual Networks
    - Load Balancers
    - Key Vaults
    """)
    
    try:
        agent = AzureTerraformAgent()
    except Exception as e:
        st.error(f"Failed to initialize Azure Terraform Agent: {str(e)}")
        st.stop()
    
    # Store generated configurations to avoid regenerating on download
    if "current_terraform_code" not in st.session_state:
        st.session_state.current_terraform_code = ""
    if "current_tfvars_content" not in st.session_state:
        st.session_state.current_tfvars_content = ""
    
    # Always display download buttons for the latest configuration if available
    if st.session_state.current_terraform_code and st.session_state.current_tfvars_content:
        st.sidebar.markdown("### Download Files")
        st.sidebar.download_button(
            label="Download Resources",
            data=st.session_state.current_terraform_code,
            file_name="resources.tf",
            mime="text/plain",
            key="sidebar_resources"
        )
        st.sidebar.download_button(
            label="Download Main Config",
            data=agent.get_main_tf_content(),
            file_name="main.tf",
            mime="text/plain",
            key="sidebar_main"
        )
        st.sidebar.download_button(
            label="Download Variables",
            data=st.session_state.current_tfvars_content,
            file_name="terraform.tfvars",
            mime="text/plain",
            key="sidebar_tfvars"
        )
    
    # Add base main.tf download option
    with st.sidebar.expander("📄 Base Terraform Configuration"):
        st.markdown("Download the base Terraform configuration with provider setup and variable declarations.")
        st.download_button(
            label="Download Base Configuration",
            data=agent.get_main_tf_content(),
            file_name="main.tf",
            mime="text/plain",
            key="download_base_expander"
        )
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Describe your Azure infrastructure needs"):
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.spinner("Processing your request..."):
            try:
                # Generate Terraform code
                terraform_code, tfvars_content = agent.generate_terraform(prompt)
                
                # Store the generated configurations
                st.session_state.current_terraform_code = terraform_code
                st.session_state.current_tfvars_content = tfvars_content
                
                # Display generated code
                with st.chat_message("assistant"):
                    st.markdown("### Generated Terraform Configuration")
                    st.code(terraform_code, language='hcl')
                    
                    # Display tfvars content
                    st.markdown("### Variable Values (terraform.tfvars)")
                    st.code(tfvars_content, language='hcl')
                    
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"Generated Terraform Configuration:\n```hcl\n{terraform_code}\n```"
                    })
                    
                    st.info("""
                    To use this configuration:
                    1. Download all three files from the sidebar (main.tf, resources.tf, and terraform.tfvars)
                    2. Place them in the same directory
                    3. Customize the terraform.tfvars file with your actual values
                    4. Initialize Terraform: `terraform init`
                    5. Review the plan: `terraform plan`
                    6. Apply the configuration: `terraform apply`
                    """)
                    
            except ValueError as e:
                with st.chat_message("assistant"):
                    st.warning(str(e))
                    st.markdown("""
                    Please ensure your query is related to Azure infrastructure deployment and includes supported resources:
                    - Resource Groups
                    - Virtual Machines
                    - AKS (Azure Kubernetes Service)
                    - Storage Accounts
                    - Virtual Networks
                    - Load Balancers
                    - Key Vaults
                    """)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"⚠️ {str(e)}"
                    })
            except Exception as e:
                st.error(f"Error generating Terraform configuration: {str(e)}")

if __name__ == "__main__":
    azure_terraform_chat() 