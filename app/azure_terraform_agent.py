import os
import streamlit as st
from dotenv import load_dotenv
from rag_engine import TerraformRAGEngine
from openai import AzureOpenAI
from langchain.prompts import ChatPromptTemplate
import base64
import pyperclip

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
        Returns a tuple of (terraform_code, tfvars_content, tfvars_filename)
        """
        # Check for specific resource types
        is_resource_group_request = "resource group" in user_input.lower()
        is_storage_account_request = "storage account" in user_input.lower() or "storage accounts" in user_input.lower()
        is_key_vault_request = "key vault" in user_input.lower() or "keyvault" in user_input.lower()
        
        # Determine the tfvars filename based on resource type
        tfvars_filename = "terraform.tfvars"
        
        if is_resource_group_request:
            tfvars_filename = "resource_group.auto.tfvars"
        elif is_storage_account_request:
            tfvars_filename = "storage_account.auto.tfvars"
        elif is_key_vault_request:
            tfvars_filename = "key_vault.auto.tfvars"
        
        # For specific resource types, we directly get the tfvars
        if is_resource_group_request:
            # For resource groups, get both the main config and tfvars
            configs = self.rag_engine._generate_resource_group_config(user_input)
            
            # Check if we need to generate Entra groups
            if "role_assignments" in configs['tfvars'] and "{}" not in configs['tfvars']:
                # Generate Entra groups configuration
                entra_configs = self.rag_engine._generate_entra_groups_config(configs['tfvars'])
                return "", configs['tfvars'], tfvars_filename, entra_configs['tfvars']
            
            return "", configs['tfvars'], tfvars_filename, ""
            
        elif is_storage_account_request:
            # For storage accounts, get both the main config and tfvars
            configs = self.rag_engine._generate_storage_account_config(user_input)
            return "", configs['tfvars'], tfvars_filename, ""
            
        elif is_key_vault_request:
            # For Key Vaults, get both the main config and tfvars
            configs = self.rag_engine._generate_key_vault_config(user_input)
            return "", configs['tfvars'], tfvars_filename, ""
            
        else:
            # For other resources, use the standard flow
            terraform_code = self.rag_engine.generate_terraform(user_input)
            tfvars_content = self._extract_variables(terraform_code)
            return terraform_code, tfvars_content, tfvars_filename, ""
    
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

# Define copy functions for the clipboard
def copy_to_clipboard(text):
    """Copy text to clipboard using pyperclip with JavaScript fallback"""
    try:
        # Try to use pyperclip first
        pyperclip.copy(text)
        st.toast("Copied to clipboard successfully!", icon="✅")
    except Exception as e:
        # Fallback to JavaScript method
        escaped_text = text.replace('`', '\\`').replace('$', '\\$').replace('{', '\\{').replace('}', '\\}')
        js_code = f"""
        <script>
        function copyToClipboard() {{
            const textArea = document.createElement('textarea');
            textArea.value = `{escaped_text}`;
            document.body.appendChild(textArea);
            textArea.select();
            try {{
                document.execCommand('copy');
                console.log('Copied to clipboard');
            }} catch (err) {{
                console.error('Failed to copy: ', err);
            }}
            document.body.removeChild(textArea);
        }}
        copyToClipboard();
        </script>
        """
        st.components.v1.html(js_code, height=0)
        st.toast("Copied to clipboard!", icon="✅")

def get_download_link(content, filename):
    """Create a download link for a text file"""
    b64 = base64.b64encode(content.encode()).decode()
    return f'<a href="data:file/txt;base64,{b64}" download="{filename}">Download {filename}</a>'

# Streamlit UI Component
def azure_terraform_chat():
    st.title("Azure Terraform Generator")
    
    # Add chat controls to the top-right corner
    chat_control_container = st.container()
    with chat_control_container:
        col1, col2 = st.columns([9, 1])
        with col2:
            if st.button("🗑️ Clear Chat", key="clear_chat", help="Clear chat history"):
                # Clear chat history and generated code
                st.session_state.messages = []
                st.session_state.current_terraform_code = ""
                st.session_state.current_tfvars_content = ""
                st.session_state.current_entra_tfvars_content = ""
                st.session_state.current_tfvars_filename = "terraform.tfvars"
                st.rerun()
    
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
    if "current_entra_tfvars_content" not in st.session_state:
        st.session_state.current_entra_tfvars_content = ""
    if "current_tfvars_filename" not in st.session_state:
        st.session_state.current_tfvars_filename = "terraform.tfvars"
    
    # Initialize messages if not present
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Always display download buttons for the latest configuration if available
    if st.session_state.current_terraform_code and st.session_state.current_tfvars_content:
        st.sidebar.markdown("### Download Files")
        st.sidebar.download_button(
            label="📥 Download Resources",
            data=st.session_state.current_terraform_code,
            file_name="resources.tf",
            mime="text/plain",
            key="sidebar_resources"
        )
        
        st.sidebar.download_button(
            label="📥 Download Main Config",
            data=agent.get_main_tf_content(),
            file_name="main.tf",
            mime="text/plain",
            key="sidebar_main"
        )
        
        st.sidebar.download_button(
            label="📥 Download Variables",
            data=st.session_state.current_tfvars_content,
            file_name=st.session_state.current_tfvars_filename,
            mime="text/plain",
            key="sidebar_tfvars"
        )
        
        if st.session_state.current_entra_tfvars_content:
            st.sidebar.download_button(
                label="📥 Download Entra Groups",
                data=st.session_state.current_entra_tfvars_content,
                file_name="entra_groups.auto.tfvars",
                mime="text/plain",
                key="sidebar_entra"
            )
    
    # Add base main.tf download option
    with st.sidebar.expander("📄 Base Terraform Configuration"):
        st.markdown("Download the base Terraform configuration with provider setup and variable declarations.")
        st.download_button(
            label="📥 Download Base Configuration",
            data=agent.get_main_tf_content(),
            file_name="main.tf",
            mime="text/plain",
            key="download_base_expander"
        )
    
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
                terraform_code, tfvars_content, tfvars_filename, entra_configs = agent.generate_terraform(prompt)
                
                # Store the generated configurations
                st.session_state.current_terraform_code = terraform_code
                st.session_state.current_tfvars_content = tfvars_content
                st.session_state.current_tfvars_filename = tfvars_filename
                st.session_state.current_entra_tfvars_content = entra_configs
                
                # Display generated code
                with st.chat_message("assistant"):
                    # Only show the terraform configuration section if there's code to display
                    if terraform_code:
                        st.markdown("### Generated Terraform Configuration")
                        st.code(terraform_code, language='hcl')
                    
                    # Display tfvars content
                    st.markdown(f"### Variable Values ({tfvars_filename})")
                    st.code(tfvars_content, language='hcl')
                    
                    # Display Entra groups content if available
                    if entra_configs:
                        st.markdown("### Entra Groups Configuration")
                        st.code(entra_configs, language='hcl')
                    
                    # Store only non-empty content in the chat history
                    content = ""
                    if terraform_code:
                        content += f"Generated Terraform Configuration:\n```hcl\n{terraform_code}\n```\n\n"
                    content += f"Variable Values ({tfvars_filename}):\n```hcl\n{tfvars_content}\n```"
                    if entra_configs:
                        content += f"\n\nEntra Groups Configuration:\n```hcl\n{entra_configs}\n```"
                    
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": content
                    })
                    
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