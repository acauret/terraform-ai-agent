import os
import re
from abc import ABC, abstractmethod
from langchain.llms import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

class Agent(ABC):
    def __init__(self, templates_dir):
        """
        Initialize the base agent.
        
        Args:
            templates_dir (str): Directory containing prompt templates
        """
        self.templates_dir = templates_dir
        self.llm = None  # Will be set by the calling application
        
    def set_llm(self, llm):
        """
        Set the language model to use for predictions.
        
        Args:
            llm: Language model instance with a predict method
        """
        self.llm = llm
    
    @abstractmethod
    def generate_config(self, query):
        """
        Generate Terraform configuration based on the query.
        
        Args:
            query (str): User's natural language query
            
        Returns:
            dict: Configuration details
        """
        pass
    
    def _load_prompt_file(self, filename):
        """
        Load prompt template from file.
        
        Args:
            filename (str): Name of the prompt file
            
        Returns:
            str: Content of the prompt file, or empty string if file not found
        """
        file_path = os.path.join(self.templates_dir, filename)
        try:
            with open(file_path, 'r') as file:
                return file.read()
        except Exception as e:
            print(f"Error loading prompt file {filename}: {str(e)}")
            return ""
            
    def _validate_response_format(self, response, expected_pattern, fallback_func=None, *fallback_args):
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
        # Check if response matches the expected pattern
        if re.search(expected_pattern, response, re.DOTALL):
            return True, None
            
        # If fallback function is provided, call it
        if fallback_func is not None:
            fallback_result = fallback_func(*fallback_args)
            return False, fallback_result
            
        return False, None

class SpecializedAgent(Agent):
    def __init__(self, templates_dir):
        super().__init__(templates_dir)
        self.llm = AzureOpenAI(
            deployment_name=os.getenv("OPENAI_DEPLOYMENT_NAME", "gpt-35-turbo"),
            model_name=os.getenv("OPENAI_MODEL_NAME", "gpt-35-turbo"),
            openai_api_version=os.getenv("OPENAI_API_VERSION", "2023-05-15"),
            temperature=0.2
        )
        
    def generate_config(self, query):
        """
        Generate Terraform configuration based on the query.
        This method should be implemented by each specialized agent.
        
        Args:
            query (str): User's natural language query
            
        Returns:
            dict: Configuration details including main_config, tfvars, etc.
        """
        raise NotImplementedError("Subclasses must implement generate_config()") 