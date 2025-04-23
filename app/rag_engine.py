import os
from typing import List, Dict, Tuple
import streamlit as st
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import AzureOpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_openai import AzureChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
import re  # Move re import to the top of the file

class TerraformRAGEngine:
    def __init__(self, template_dir: str):
        """Initialize the RAG engine with template directory."""
        self.template_dir = template_dir
        
        # Verify Azure OpenAI configuration
        required_vars = [
            'AZURE_OPENAI_API_KEY',
            'AZURE_OPENAI_ENDPOINT',
            'AZURE_OPENAI_CHAT_DEPLOYMENT_NAME',
            'AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME'
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        try:
            self.embeddings = AzureOpenAIEmbeddings(
                azure_deployment=os.getenv('AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME'),
                openai_api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2023-05-15'),
                azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
                api_key=os.getenv('AZURE_OPENAI_API_KEY')
            )
            # Test the embeddings
            test_result = self.embeddings.embed_query("test")
            if not test_result:
                raise ValueError("Failed to generate embeddings")
        except Exception as e:
            raise ValueError(f"Failed to initialize Azure OpenAI embeddings: {str(e)}")
            
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""]
        )
        
        try:
            self.llm = AzureChatOpenAI(
                deployment_name=os.getenv('AZURE_OPENAI_CHAT_DEPLOYMENT_NAME'),
                openai_api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2023-05-15'),
                azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
                api_key=os.getenv('AZURE_OPENAI_API_KEY'),
                temperature=0
            )
        except Exception as e:
            raise ValueError(f"Failed to initialize AzureChatOpenAI: {str(e)}")
            
        self.vector_store = None
        self._initialize_vector_store()

    def _validate_query(self, query: str) -> Tuple[bool, str]:
        """
        Validate if the query is related to Azure infrastructure and within scope.
        Returns a tuple of (is_valid, reason).
        """
        validation_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a query validator for an Azure Infrastructure Generator.
            Determine if the user's query is about Azure infrastructure deployment and within the scope of these resources:
            - Resource Groups
            - Virtual Machines
            - AKS (Azure Kubernetes Service)
            - Storage Accounts
            - Virtual Networks
            - Load Balancers

            Respond with only true or false, followed by a brief reason.
            Format: valid: <true/false>
            reason: <brief explanation>

            Examples of valid queries:
            - "Create a resource group in East US"
            - "Create a virtual machine with 2 cores"
            - "Set up a storage account with private endpoints"
            - "Deploy an AKS cluster with 3 nodes"

            Examples of invalid queries:
            - "What's the weather today?"
            - "Help me with my homework"
            - "How do I cook pasta?"
            """),
            ("human", "{query}")
        ])

        try:
            result = self.llm.invoke(validation_prompt.format(query=query))
            response_lines = result.content.strip().lower().split('\n')
            
            is_valid = False
            reason = "Invalid query format"
            
            for line in response_lines:
                if line.startswith('valid:'):
                    is_valid = 'true' in line.lower()
                elif line.startswith('reason:'):
                    reason = line[7:].strip()
            
            return is_valid, reason
        except Exception as e:
            return False, f"Error validating query: {str(e)}"

    def _load_templates(self) -> List[Document]:
        """Load all Terraform templates as documents."""
        documents = []
        tfvars_files = {}
        
        # First, load all .tfvars files and associate them with their template types
        for filename in os.listdir(self.template_dir):
            if filename.endswith('.tfvars'):
                template_type = filename.replace('.tfvars', '')
                file_path = os.path.join(self.template_dir, filename)
                with open(file_path, 'r') as f:
                    tfvars_files[template_type] = f.read()
        
        # Then load all .tf files, attaching associated .tfvars content if available
        for filename in os.listdir(self.template_dir):
            if filename.endswith('.tf'):
                file_path = os.path.join(self.template_dir, filename)
                with open(file_path, 'r') as f:
                    content = f.read()
                    
                    # Store the template type in metadata
                    template_type = filename.replace('.tf', '')
                    
                    # Attach .tfvars content if available
                    metadata = {
                        "source": filename, 
                        "type": template_type
                    }
                    
                    # If we have an associated .tfvars file, include it in the metadata
                    if template_type in tfvars_files:
                        metadata["tfvars"] = tfvars_files[template_type]
                    
                    doc = Document(
                        page_content=content,
                        metadata=metadata
                    )
                    documents.append(doc)
        return documents

    def _initialize_vector_store(self):
        """Initialize the vector store with chunked documents."""
        try:
            # Create a persistent directory for the database
            db_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db')
            os.makedirs(db_dir, exist_ok=True)
            
            documents = self._load_templates()
            splits = self.text_splitter.split_documents(documents)
            
            # Use persistent storage for the vector database
            # Chroma 0.4.x+ automatically persists documents
            self.vector_store = Chroma.from_documents(
                documents=splits,
                embedding=self.embeddings,
                persist_directory=db_dir
            )
            
        except Exception as e:
            st.error(f"Error initializing vector store: {str(e)}")
            # Fallback to in-memory storage if persistent storage fails
            try:
                documents = self._load_templates()
                splits = self.text_splitter.split_documents(documents)
                self.vector_store = Chroma.from_documents(
                    documents=splits,
                    embedding=self.embeddings
                )
            except Exception as inner_e:
                raise ValueError(f"Failed to initialize vector store: {str(inner_e)}")

    def _get_relevant_templates(self, query: str) -> List[str]:
        """Get relevant template types based on the query."""
        try:
            template_prompt = ChatPromptTemplate.from_messages([
                ("system", """Analyze the user's infrastructure requirements and identify which Azure resource types are needed.
                Return a comma-separated list of resource types from these options only: virtual_machine, aks, storage, vnet, lb.
                Example: "storage,vnet" if user needs storage and networking."""),
                ("human", "{input}")
            ])
            
            chain = template_prompt | self.llm
            result = chain.invoke({"input": query})
            
            if not result.content:
                return ["virtual_machine"]  # Default to basic resources if no clear match
                
            return [t.strip() for t in result.content.split(',')]
            
        except Exception as e:
            st.error(f"Error in template selection: {str(e)}")
            return ["virtual_machine"]  # Default to basic resources on error

    def _generate_entra_groups_config(self, resource_group_tfvars: str) -> Dict[str, str]:
        """Generate Terraform configuration for Entra ID groups based on role assignments in resource groups."""
        try:
            # Debug the input
            if hasattr(st.session_state, 'debug_mode') and st.session_state.debug_mode:
                st.write("Debug: Input to _generate_entra_groups_config:")
                st.code(resource_group_tfvars, language='hcl')
            
            # Load the Entra groups prompt file
            prompt_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'entra_groups_prompt.txt')
            try:
                with open(prompt_file_path, 'r') as f:
                    system_prompt = f.read()
            except Exception as e:
                st.error(f"Error reading Entra groups prompt file: {str(e)}")
                system_prompt = "Generate Terraform code for Azure Entra ID groups."
            
            # Define a local debug print function
            def debug_print(*args, **kwargs):
                if hasattr(st.session_state, 'debug_mode') and st.session_state.debug_mode:
                    st.write(*args, **kwargs)
            
            # Extract role assignments from the resource group tfvars
            groups = []
            
            # First, try to find the role_assignments block
            role_assignments_match = re.search(r'role_assignments\s*=\s*{([^}]*)}', resource_group_tfvars, re.DOTALL)
            if role_assignments_match:
                role_assignments_content = role_assignments_match.group(1)
                debug_print(f"Found role assignments content: {role_assignments_content}")
                
                # Now find all group blocks within the role_assignments
                group_pattern = r'(\w+)\s*=\s*{\s*resourcename\s*=\s*"([^"]+)"\s*role_definition_id_or_name\s*=\s*"([^"]+)"\s*principal_id\s*=\s*"([^"]+)"\s*}'
                group_matches = re.finditer(group_pattern, role_assignments_content)
                
                for match in group_matches:
                    group_key = match.group(1)  # The key in the role_assignments map
                    group_name = match.group(2)  # The resourcename
                    role = match.group(3)  # role_definition_id_or_name
                    debug_print(f"Found group: key={group_key}, name={group_name}, role={role}")
                    groups.append((group_key, group_name, role))
            
            if not groups:
                # If no groups were found with the detailed pattern, try a simpler pattern
                debug_print("No groups found with detailed pattern, trying simpler pattern")
                group_pattern = r'(\w+)\s*=\s*{([^}]*?role_definition_id_or_name\s*=\s*"([^"]+)"[^}]*)}'
                group_matches = re.finditer(group_pattern, resource_group_tfvars, re.DOTALL)
                
                for match in group_matches:
                    group_key = match.group(1)
                    group_content = match.group(2)
                    role = match.group(3)
                    # Try to extract the resourcename
                    name_match = re.search(r'resourcename\s*=\s*"([^"]+)"', group_content)
                    group_name = name_match.group(1) if name_match else group_key
                    debug_print(f"Found group with simpler pattern: key={group_key}, name={group_name}, role={role}")
                    groups.append((group_key, group_name, role))
            
            if not groups:
                # If still no groups, try one more pattern
                debug_print("No groups found with simpler pattern, trying one more pattern")
                group_pattern = r'(\w+)\s*=\s*{([^}]*)}'
                group_matches = re.finditer(group_pattern, resource_group_tfvars, re.DOTALL)
                
                for match in group_matches:
                    group_key = match.group(1)
                    group_content = match.group(2)
                    role_match = re.search(r'role_definition_id_or_name\s*=\s*"([^"]+)"', group_content)
                    name_match = re.search(r'resourcename\s*=\s*"([^"]+)"', group_content)
                    if role_match and name_match:
                        role = role_match.group(1)
                        group_name = name_match.group(1)
                        debug_print(f"Found group with final pattern: key={group_key}, name={group_name}, role={role}")
                        groups.append((group_key, group_name, role))
            
            if not groups:
                debug_print("No groups found in any pattern, returning empty configuration")
                return {"main_config": "", "tfvars": "", "tfvars_filename": "entra_groups.auto.tfvars"}
            
            # Create the user prompt with all role assignments
            user_prompt = "Generate Entra groups for the following role assignments:\n"
            for group_key, group_name, role in groups:
                user_prompt += f"- {group_name} ({role})\n"
            
            debug_print(f"Generated user prompt: {user_prompt}")
            
            # Skip LLM call and manually generate groups for consistency and reliability
            debug_print("Generating Entra groups manually for guaranteed format")
            
            # Use a dictionary to track unique groups by name to prevent duplicates
            unique_groups = {}
            for group_key, group_name, role in groups:
                if group_name not in unique_groups:
                    unique_groups[group_name] = {
                        "name": group_name,
                        "role": role
                    }
            
            # Generate content only for unique groups
            groups_content = []
            for group_name, group_info in unique_groups.items():
                groups_content.append(f"""  {group_name} = {{
    display_name = "{group_name}"
    description  = "{group_info['role']} role for {group_name}"
    owners       = ["00000000-0000-0000-0000-000000000000"]
  }}""")
                
            tfvars = "entra_groups = {\n" + ",\n".join(groups_content) + "\n}"
            debug_print(f"Manually generated tfvars: {tfvars}")
            
            # Debug the output
            result = {
                "main_config": "",  # No main.tf needed
                "tfvars": tfvars,
                "tfvars_filename": "entra_groups.auto.tfvars"
            }
            debug_print("Debug: Returning from _generate_entra_groups_config:")
            if hasattr(st.session_state, 'debug_mode') and st.session_state.debug_mode:
                st.json(result)
                
            # For Entra groups, we only need the tfvars file
            return result
            
        except Exception as e:
            st.error(f"Error generating Entra groups configuration: {str(e)}")
            raise Exception(f"Failed to generate Entra groups configuration: {str(e)}")

    def _generate_resource_group_config(self, query: str) -> Dict[str, str]:
        """Generate Terraform configuration specifically for resource groups using a prompt file."""
        try:
            # Load the resource group prompt file
            prompt_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'resource_group_prompt.txt')
            try:
                with open(prompt_file_path, 'r') as f:
                    system_prompt = f.read()
            except Exception as e:
                st.error(f"Error reading prompt file: {str(e)}")
                system_prompt = "Generate Terraform code for an Azure resource group."
            
            # Create the user prompt with the original query
            user_prompt = query
            
            # Generate the Terraform configuration using the LLM
            try:
                response = self.llm.invoke(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                
                # The response should be the raw tfvars content without any markdown
                tfvars = response.content.strip()
                
                # Validate that the response contains the expected format
                if not tfvars.startswith("resource_groups"):
                    # Attempt to extract just the content if it's wrapped in markdown
                    match = re.search(r'```(?:hcl)?\s*(resource_groups.*?)\s*```', tfvars, re.DOTALL)
                    if match:
                        tfvars = match.group(1).strip()
                    else:
                        # Fall back to a template if the format is incorrect
                        extracted_name = "my-project"
                        extracted_location = "eastus"
                        
                        # Try to extract name and location from the query
                        if "called" in query.lower() and "'" in query:
                            parts = query.split("'")
                            if len(parts) >= 3:
                                extracted_name = parts[1]
                        
                        if "in" in query.lower():
                            location_parts = query.lower().split(" in ")
                            if len(location_parts) >= 2:
                                location_candidate = location_parts[1].strip().split()[0]
                                if location_candidate in ["east", "west", "north", "south", "central"]:
                                    extracted_location = location_candidate + "us"
                        
                        tfvars = f"""resource_groups = {{
  # Resource group details
  rg01 = {{
    name     = "{extracted_name}"
    location = "{extracted_location}"
    role_assignments = {{}}
  }}
}}"""
                
                # For resource groups, we only need the tfvars file
                return {
                    "main_config": "",  # No main.tf needed
                    "tfvars": tfvars,
                    "tfvars_filename": "resource_groups.auto.tfvars"
                }
                
            except Exception as e:
                st.error(f"Error generating Terraform with LLM: {str(e)}")
                raise Exception(f"Failed to generate Terraform configuration: {str(e)}")
            
        except Exception as e:
            st.error(f"Error generating resource group configuration: {str(e)}")
            raise Exception(f"Failed to generate resource group configuration: {str(e)}")

    def _generate_storage_account_config(self, query: str) -> Dict[str, str]:
        """Generate Terraform configuration specifically for storage accounts using a prompt file."""
        try:
            # Load the storage account prompt file
            prompt_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'storage_account_prompt.txt')
            try:
                with open(prompt_file_path, 'r') as f:
                    system_prompt = f.read()
            except Exception as e:
                st.error(f"Error reading storage account prompt file: {str(e)}")
                system_prompt = "Generate Terraform code for Azure storage accounts."
            
            # Create the user prompt with the original query
            user_prompt = query
            
            # Generate the Terraform configuration using the LLM
            try:
                response = self.llm.invoke(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                
                # The response should be the raw tfvars content without any markdown
                tfvars = response.content.strip()
                
                # Validate that the response contains the expected format
                if not tfvars.startswith("storage_accounts"):
                    # Attempt to extract just the content if it's wrapped in markdown
                    match = re.search(r'```(?:hcl)?\s*(storage_accounts.*?)\s*```', tfvars, re.DOTALL)
                    if match:
                        tfvars = match.group(1).strip()
                    else:
                        # Fall back to a template if the format is incorrect
                        # Try to extract name and resource group from the query
                        extracted_name = "st01"
                        extracted_rg = "rg01"
                        
                        if "called" in query.lower() and "'" in query:
                            parts = query.split("'")
                            if len(parts) >= 3:
                                extracted_name = parts[1]
                        
                        if "in" in query.lower() and "resource group" in query.lower():
                            rg_parts = query.lower().split("resource group")
                            if len(rg_parts) >= 2:
                                rg_candidate = rg_parts[1].strip().split()[0]
                                if rg_candidate:
                                    extracted_rg = rg_candidate
                        
                        tfvars = f"""storage_accounts = {{
  st01 = {{
    name                      = "{extracted_name}"
    resource_group_key        = "{extracted_rg}"
    access_tier               = "Hot"
    account_kind              = "StorageV2"
    account_replication_type  = "ZRS"
    account_tier              = "Standard"

    private_endpoints = {{
      blob = {{
        subresource_name = "blob"
      }},
      queue = {{
        subresource_name = "queue"
      }},
      table = {{
        subresource_name = "table"
      }},
      file = {{
        subresource_name = "file"
      }}
    }}
    container = {{}}

    role_assignments = {{}}
  }}
}}"""
                
                # Check if role assignments are present in the tfvars
                role_assignments_match = re.search(r'role_assignments\s*=\s*{([^}]*)}', tfvars, re.DOTALL)
                if role_assignments_match and role_assignments_match.group(1).strip():
                    # If role assignments are present, generate Entra groups configuration
                    entra_configs = self._generate_entra_groups_config(tfvars)
                    return {
                        "main_config": "",  # No main.tf needed
                        "tfvars": tfvars,
                        "tfvars_filename": "storage_accounts.auto.tfvars",
                        "entra_configs": entra_configs
                    }
                
                # For storage accounts without role assignments, we only need the tfvars file
                return {
                    "main_config": "",  # No main.tf needed
                    "tfvars": tfvars,
                    "tfvars_filename": "storage_accounts.auto.tfvars",
                    "entra_configs": {"main_config": "", "tfvars": "", "tfvars_filename": "entra_groups.auto.tfvars"}
                }
                
            except Exception as e:
                st.error(f"Error generating storage account config with LLM: {str(e)}")
                raise Exception(f"Failed to generate storage account configuration: {str(e)}")
            
        except Exception as e:
            st.error(f"Error generating storage account configuration: {str(e)}")
            raise Exception(f"Failed to generate storage account configuration: {str(e)}")

    def _generate_key_vault_config(self, query: str) -> str:
        """Generate Terraform configuration specifically for Key Vaults using a prompt file."""
        try:
            # Load the Key Vault prompt file
            prompt_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'key_vault_prompt.txt')
            try:
                with open(prompt_file_path, 'r') as f:
                    system_prompt = f.read()
            except Exception as e:
                st.error(f"Error reading Key Vault prompt file: {str(e)}")
                system_prompt = "Generate Terraform code for Azure Key Vaults."
            
            # Create the user prompt with the original query
            user_prompt = query
            
            # Generate the Terraform configuration using the LLM
            try:
                response = self.llm.invoke(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                
                # The response should be the raw tfvars content without any markdown
                tfvars = response.content.strip()
                
                # Validate that the response contains the expected format
                if not tfvars.startswith("key_vault"):
                    # Attempt to extract just the content if it's wrapped in markdown
                    match = re.search(r'```(?:hcl)?\s*(key_vault.*?)\s*```', tfvars, re.DOTALL)
                    if match:
                        tfvars = match.group(1).strip()
                    else:
                        # Fall back to a template if the format is incorrect
                        tfvars = """key_vault = {
  kv-default = {
    name               = "kv-default"
    resource_group_key = "rg01"

    private_endpoints = {
      vault = {
        subresource_name = "vault"
      }
    }
    network_acls        = {}
    diagnostic_settings = {}

    role_assignments = {}
  }
}"""
                
                # For Key Vaults, we only need the tfvars file
                return {
                    "main_config": "",  # No main.tf needed
                    "tfvars": tfvars,
                    "tfvars_filename": "key_vault.auto.tfvars"
                }
                
            except Exception as e:
                st.error(f"Error generating Key Vault config with LLM: {str(e)}")
                raise Exception(f"Failed to generate Key Vault configuration: {str(e)}")
            
        except Exception as e:
            st.error(f"Error generating Key Vault configuration: {str(e)}")
            raise Exception(f"Failed to generate Key Vault configuration: {str(e)}")

    def generate_terraform(self, query: str) -> Dict[str, str]:
        """Generate Terraform configuration using RAG."""
        try:
            # First, validate the query
            is_valid, reason = self._validate_query(query)
            if not is_valid:
                raise ValueError(f"Query is out of scope: {reason}")

            # Check if this is a resource group request
            is_resource_group_request = "resource group" in query.lower()
            
            # Check if this is a storage account request
            is_storage_account_request = "storage account" in query.lower() or "storage accounts" in query.lower()
            
            # Check if this is a Key Vault request
            is_key_vault_request = "key vault" in query.lower() or "keyvault" in query.lower()
            
            # Updated to return a dictionary with all configurations
            result = {
                "main_config": "",
                "configs": []
            }
            
            # Handling resource group requests directly with the prompt-based approach
            if is_resource_group_request:
                # For resource groups, we need both the resource group and Entra groups configs
                configs = self._generate_resource_group_config(query)
                result["configs"].append({
                    "type": "resource_group",
                    "content": configs["tfvars"],
                    "filename": configs["tfvars_filename"]
                })
                
                # Check if role assignments are present and generate Entra groups
                role_assignments_match = re.search(r'role_assignments\s*=\s*{([^}]*)}', configs['tfvars'], re.DOTALL)
                if role_assignments_match and role_assignments_match.group(1).strip():
                    entra_configs = self._generate_entra_groups_config(configs['tfvars'])
                    result["configs"].append({
                        "type": "entra_groups",
                        "content": entra_configs["tfvars"],
                        "filename": entra_configs["tfvars_filename"]
                    })
                
                # For backwards compatibility, return the combined config as a string
                combined = ""
                for config in result["configs"]:
                    combined += f"# {config['type'].replace('_', ' ').title()} Configuration\n{config['content']}\n\n"
                return combined.strip()
            
            # Handling storage account requests with the prompt-based approach
            elif is_storage_account_request:
                # For storage accounts, we need both the storage account and Entra groups configs
                configs = self._generate_storage_account_config(query)
                result["configs"].append({
                    "type": "storage_account",
                    "content": configs["tfvars"],
                    "filename": configs["tfvars_filename"]
                })
                
                # Check if role assignments are present and generate Entra groups
                role_assignments_match = re.search(r'role_assignments\s*=\s*{([^}]*)}', configs['tfvars'], re.DOTALL)
                if role_assignments_match and role_assignments_match.group(1).strip():
                    st.write("Found role assignments in storage account, generating Entra groups")
                    entra_configs = self._generate_entra_groups_config(configs['tfvars'])
                    result["configs"].append({
                        "type": "entra_groups",
                        "content": entra_configs["tfvars"],
                        "filename": entra_configs["tfvars_filename"]
                    })
                
                # For backwards compatibility, return the combined config as a string
                combined = ""
                for config in result["configs"]:
                    combined += f"# {config['type'].replace('_', ' ').title()} Configuration\n{config['content']}\n\n"
                return combined.strip()
                
            # Handling Key Vault requests with the prompt-based approach
            elif is_key_vault_request:
                # For Key Vaults, we only need the tfvars file
                configs = self._generate_key_vault_config(query)
                result["configs"].append({
                    "type": "key_vault",
                    "content": configs["tfvars"],
                    "filename": configs["tfvars_filename"]
                })
                
                # For backwards compatibility, return the combined config as a string
                combined = ""
                for config in result["configs"]:
                    combined += f"# {config['type'].replace('_', ' ').title()} Configuration\n{config['content']}\n\n"
                return combined.strip()
                
            # For other resources, get relevant template types
            relevant_types = self._get_relevant_templates(query)
            
            # Create a retriever that focuses on relevant templates
            retriever = self.vector_store.as_retriever(
                search_type="similarity",
                search_kwargs={
                    "k": 5,
                    "filter": {"type": {"$in": relevant_types}}
                }
            )

            # Create the prompt for generating Terraform code
            system_prompt = """You are a Terraform expert. Using the provided reference templates and variable files, generate a complete Terraform configuration for Azure.
            
            For each template, check if there are associated variable values (.tfvars) content in the metadata["tfvars"] field.
            If .tfvars data is available, use those values as defaults or examples when generating your configuration.
            
            The configuration should:
            1. Include all necessary variable declarations
            2. Follow Terraform best practices
            3. Include helpful comments
            4. Be properly formatted
            5. Maintain consistency with the reference templates
            6. Use variable values from .tfvars files where appropriate"""

            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", "{input}")
            ])

            # Create a chain to combine documents
            document_chain = create_stuff_documents_chain(
                llm=self.llm,
                prompt=prompt,
            )

            # Create the retrieval chain
            retrieval_chain = create_retrieval_chain(
                retriever,
                document_chain
            )

            # Generate the response
            response = retrieval_chain.invoke({
                "input": query
            })

            if "answer" not in response:
                raise ValueError("No response generated from the model")

            return response["answer"]
            
        except ValueError as e:
            # Re-raise validation errors to be handled by the UI
            raise
        except Exception as e:
            st.error(f"Error in generate_terraform: {str(e)}")
            raise Exception(f"Failed to generate Terraform configuration: {str(e)}") 