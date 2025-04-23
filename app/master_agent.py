import os
import streamlit as st
from typing import Dict, List, Any
import re
import dotenv
from rag_engine import TerraformRAGEngine

# Load environment variables from .env file
dotenv.load_dotenv()

class MasterAgent:
    def __init__(self, template_dir: str):
        """Initialize the master agent with a template directory."""
        self.template_dir = template_dir
        self.terraform_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'terraform')
        self.main_tf_path = os.path.join(self.terraform_dir, 'main.tf')
        
        if not os.path.exists(self.main_tf_path):
            st.warning(f"Base Terraform configuration not found: {self.main_tf_path}")
        
        try:    
            self.rag_engine = TerraformRAGEngine(template_dir)
        except Exception as e:
            st.error(f"Error initializing RAG engine: {str(e)}")
            st.warning("Continuing with limited functionality.")
            self.rag_engine = None
        
    def get_main_tf_content(self) -> str:
        """Get the content of the main.tf file from the terraform directory."""
        try:
            with open(self.main_tf_path, 'r') as f:
                return f.read()
        except Exception as e:
            st.error(f"Error reading main.tf: {str(e)}")
            return "# Error loading main.tf template"
        
    def _extract_resource_types(self, query: str) -> List[str]:
        """Extract the resource types mentioned in the query."""
        resource_types = []
        
        # Check for resource group
        if "resource group" in query.lower():
            resource_types.append("resource_group")
        
        # Check for storage account
        if "storage account" in query.lower() or "storage accounts" in query.lower():
            resource_types.append("storage_account")
        
        # Check for key vault
        if "key vault" in query.lower() or "keyvault" in query.lower():
            resource_types.append("key_vault")
            
        # Add more resource types as needed
        
        return resource_types
    
    def _has_role_assignments(self, config: str) -> bool:
        """Check if a configuration has role assignments."""
        role_assignments_match = re.search(r'role_assignments\s*=\s*{([^}]*)}', config, re.DOTALL)
        return role_assignments_match is not None and role_assignments_match.group(1).strip() != ""
    
    def _collect_role_assignments(self, configs: List[Dict[str, str]]) -> str:
        """Collect all role assignments from multiple configurations into a single string."""
        combined_assignments = ""
        
        for config in configs:
            if "content" in config:
                role_assignments_match = re.search(r'role_assignments\s*=\s*{([^}]*)}', config["content"], re.DOTALL)
                if role_assignments_match and role_assignments_match.group(1).strip():
                    # Add a comment to indicate the source resource
                    source = config["type"].replace("_", " ").title()
                    assignment_block = f"# Role assignments from {source}\n"
                    assignment_block += f"role_assignments = {{\n{role_assignments_match.group(1)}\n}}"
                    
                    if combined_assignments:
                        combined_assignments += "\n\n" + assignment_block
                    else:
                        combined_assignments = assignment_block
        
        return combined_assignments
    
    def process_request(self, query: str) -> Dict[str, Any]:
        """Process a user request and coordinate the appropriate agents."""
        try:
            # Check if RAG engine is available
            if self.rag_engine is None:
                st.error("RAG engine is not available. Cannot process the request.")
                return {
                    "success": False,
                    "message": "RAG engine initialization failed. Please check your Azure OpenAI API configuration.",
                    "configs": []
                }
                
            # Extract resource types from query
            resource_types = self._extract_resource_types(query)
            
            if not resource_types:
                # If no specific resource types are mentioned, use the general RAG approach
                general_result = self.rag_engine.generate_terraform(query)
                return {
                    "success": True,
                    "message": "Generated Terraform configuration",
                    "configs": [
                        {
                            "type": "general",
                            "content": general_result,
                            "filename": "main.tf"
                        }
                    ]
                }
            
            # Results will store all generated configurations
            results = {
                "configs": []
            }
            
            # Process each resource type using specialized methods
            for resource_type in resource_types:
                if resource_type == "resource_group":
                    config = self.rag_engine._generate_resource_group_config(query)
                    results["configs"].append({
                        "type": "resource_group",
                        "content": config["tfvars"],
                        "filename": config["tfvars_filename"]
                    })
                        
                elif resource_type == "storage_account":
                    config = self.rag_engine._generate_storage_account_config(query)
                    results["configs"].append({
                        "type": "storage_account",
                        "content": config["tfvars"],
                        "filename": config["tfvars_filename"]
                    })
                        
                elif resource_type == "key_vault":
                    config = self.rag_engine._generate_key_vault_config(query)
                    results["configs"].append({
                        "type": "key_vault", 
                        "content": config["tfvars"],
                        "filename": config["tfvars_filename"]
                    })
            
            # After all individual resources are processed, check if any have role assignments
            # and generate a unified Entra groups config
            all_role_assignments = self._collect_role_assignments(results["configs"])
            
            if all_role_assignments:
                # Generate Entra groups based on all role assignments
                entra_config = self.rag_engine._generate_entra_groups_config(all_role_assignments)
                results["configs"].append({
                    "type": "entra_groups",
                    "content": entra_config["tfvars"],
                    "filename": entra_config["tfvars_filename"]
                })
            
            # Format the combined output
            combined_output = self._format_output(results["configs"])
            
            # Add main.tf content to the results for downloading
            results["main_tf"] = self.get_main_tf_content()
            
            return {
                "success": True,
                "message": "Generated Terraform configurations",
                "configs": results["configs"],
                "combined": combined_output,
                "main_tf": results["main_tf"]
            }
            
        except Exception as e:
            st.error(f"Error in master agent: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to generate Terraform configuration: {str(e)}",
                "configs": []
            }
    
    def _format_output(self, configs: List[Dict[str, str]]) -> str:
        """Format multiple configurations into a single output."""
        if not configs:
            return ""
            
        combined = ""
        for config in configs:
            resource_type = config["type"].replace("_", " ").title()
            combined += f"# {resource_type} Configuration\n{config['content']}\n\n"
            
        return combined.strip() 