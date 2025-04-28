import os
import streamlit as st
from typing import Dict, Any, Optional
from langchain_openai import AzureChatOpenAI

class BaseAgent:
    """Base class for all resource-specific agents."""
    
    def __init__(self, template_dir: str, debug_mode: bool = False):
        """Initialize the base agent with a template directory and debug mode."""
        self.template_dir = template_dir
        self.debug_mode = debug_mode
        
        # Store environment variables but don't print them yet
        self.azure_api_key = os.getenv('AZURE_OPENAI_API_KEY')
        self.azure_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
        self.azure_deployment = os.getenv('AZURE_OPENAI_CHAT_DEPLOYMENT_NAME')
        self.azure_api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2023-05-15')
        
        # Initialize Azure OpenAI client without using st.error
        try:
            if not self.azure_api_key or not self.azure_endpoint or not self.azure_deployment:
                print("Missing required Azure OpenAI environment variables")
                self.llm = None
            else:
                self.llm = AzureChatOpenAI(
                    deployment_name=self.azure_deployment,
                    openai_api_version=self.azure_api_version,
                    azure_endpoint=self.azure_endpoint,
                    api_key=self.azure_api_key,
                    temperature=0
                )
        except Exception as e:
            print(f"Failed to initialize Azure OpenAI: {str(e)}")
            self.llm = None
    
    def debug_env_variables(self):
        """Print debug information about environment variables using Streamlit."""
        st.write("Checking environment variables:")
        st.write(f"API Key exists: {self.azure_api_key is not None}")
        st.write(f"Endpoint exists: {self.azure_endpoint is not None}")
        st.write(f"Deployment exists: {self.azure_deployment is not None}")
        st.write(f"API Version: {self.azure_api_version}")
        
        if not self.llm:
            st.error("LLM was not initialized properly. Cannot make predictions.")
    
    def _load_prompt_template(self, prompt_file: str) -> str:
        """Load the prompt template from a file."""
        prompt_file_path = os.path.join(self.template_dir, prompt_file)
        try:
            with open(prompt_file_path, 'r') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading prompt file {prompt_file}: {str(e)}")
            return "Generate Terraform code for the specified Azure resource."
    
    def _validate_response_format(self, response: str, expected_pattern: str, fallback_func=None, *fallback_args) -> tuple:
        """
        Validate that the response from the LLM contains the expected format.
        
        Args:
            response (str): Response from the LLM
            expected_pattern (str): Regex pattern to match against the response
            fallback_func (callable, optional): Function to call if validation fails
            *fallback_args: Arguments to pass to the fallback function
            
        Returns:
            tuple: (is_valid, fallback_result) - is_valid is a boolean indicating if validation passed,
                  fallback_result is the result from the fallback function or None
        """
        import re
        # Check if response matches the expected pattern
        if re.search(expected_pattern, response, re.DOTALL):
            return True, None
            
        # If fallback function is provided, call it
        if fallback_func is not None:
            fallback_result = fallback_func(*fallback_args)
            return False, fallback_result
            
        return False, None
    
    def generate_config(self, query: str) -> Dict[str, Any]:
        """
        Generate Terraform configuration based on user query.
        
        This method should be implemented by child classes.
        """
        raise NotImplementedError("Subclasses must implement generate_config method.")
    
    def process_role_assignments(self, config: str) -> bool:
        """Check if a configuration has role assignments."""
        import re
        role_assignments_match = re.search(r'role_assignments\s*=\s*{([^}]*)}', config, re.DOTALL)
        return role_assignments_match is not None and role_assignments_match.group(1).strip() != "" 