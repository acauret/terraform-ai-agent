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

    def _generate_resource_group_config(self, query: str) -> str:
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
                    import re
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
                    "tfvars": tfvars
                }
                
            except Exception as e:
                st.error(f"Error generating Terraform with LLM: {str(e)}")
                raise Exception(f"Failed to generate Terraform configuration: {str(e)}")
            
        except Exception as e:
            st.error(f"Error generating resource group configuration: {str(e)}")
            raise Exception(f"Failed to generate resource group configuration: {str(e)}")

    def _generate_storage_account_config(self, query: str) -> str:
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
                    import re
                    match = re.search(r'```(?:hcl)?\s*(storage_accounts.*?)\s*```', tfvars, re.DOTALL)
                    if match:
                        tfvars = match.group(1).strip()
                    else:
                        # Fall back to a template if the format is incorrect
                        tfvars = """storage_accounts = {
  st01 = {
    name                      = "st01"
    resource_group_key        = "rg01"

    private_endpoints = {
      blob = {
        subresource_name = "blob"
      },
      queue = {
        subresource_name = "queue"
      },
      table = {
        subresource_name = "table"
      },
      file = {
        subresource_name = "file"
      }
    }
    container = {}

    role_assignments = {}
  }
}"""
                
                # For storage accounts, we only need the tfvars file
                return {
                    "main_config": "",  # No main.tf needed
                    "tfvars": tfvars
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
                    import re
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
                    "tfvars": tfvars
                }
                
            except Exception as e:
                st.error(f"Error generating Key Vault config with LLM: {str(e)}")
                raise Exception(f"Failed to generate Key Vault configuration: {str(e)}")
            
        except Exception as e:
            st.error(f"Error generating Key Vault configuration: {str(e)}")
            raise Exception(f"Failed to generate Key Vault configuration: {str(e)}")

    def generate_terraform(self, query: str) -> str:
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
            
            # Handling resource group requests directly with the prompt-based approach
            if is_resource_group_request:
                # For resource groups, we only need the tfvars file
                configs = self._generate_resource_group_config(query)
                # Return the tfvars content only
                return configs['tfvars']
            
            # Handling storage account requests with the prompt-based approach
            elif is_storage_account_request:
                # For storage accounts, we only need the tfvars file
                configs = self._generate_storage_account_config(query)
                # Return the tfvars content only
                return configs['tfvars']
                
            # Handling Key Vault requests with the prompt-based approach
            elif is_key_vault_request:
                # For Key Vaults, we only need the tfvars file
                configs = self._generate_key_vault_config(query)
                # Return the tfvars content only
                return configs['tfvars']
                
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