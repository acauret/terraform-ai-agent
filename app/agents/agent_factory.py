import os
import streamlit as st
from typing import Dict, Any, List, Type
from .base_agent import BaseAgent
from .resource_group_agent import ResourceGroupAgent
from .storage_account_agent import StorageAccountAgent
from .key_vault_agent import KeyVaultAgent
from .entra_groups_agent import EntraGroupsAgent

class AgentFactory:
    """Factory class for creating and managing specialized agents."""
    
    def __init__(self, template_dir: str):
        """Initialize the agent factory with a template directory."""
        self.template_dir = template_dir
        self.agents = {
            "resource_group": ResourceGroupAgent(template_dir),
            "storage_account": StorageAccountAgent(template_dir),
            "key_vault": KeyVaultAgent(template_dir),
            "entra_groups": EntraGroupsAgent(template_dir)
        }
    
    def get_agent(self, agent_type: str) -> BaseAgent:
        """Get an agent by type."""
        if agent_type not in self.agents:
            raise ValueError(f"Unknown agent type: {agent_type}")
        return self.agents[agent_type]
    
    def extract_resource_types(self, query: str) -> List[str]:
        """Extract resource types from a query."""
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
        
        return resource_types
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """Process a query and generate configurations using appropriate agents."""
        try:
            # Extract resource types from query
            resource_types = self.extract_resource_types(query)
            
            if not resource_types:
                return {
                    "success": False,
                    "message": "No resource types identified in the query. Please specify one or more of: resource group, storage account, key vault.",
                    "configs": []
                }
                
            # Process each resource type and generate configurations
            configs = []
            role_assignments_detected = False
            role_assignments_content = ""
            
            for resource_type in resource_types:
                agent = self.get_agent(resource_type)
                config = agent.generate_config(query)
                
                configs.append({
                    "type": resource_type,
                    "content": config["tfvars"],
                    "filename": config["tfvars_filename"]
                })
                
                # Check if this resource has role assignments
                if agent.has_role_assignments(config):
                    role_assignments_detected = True
                    role_assignments_content += config["tfvars"] + "\n\n"
                    
            # If any resources had role assignments, generate Entra groups
            if role_assignments_detected:
                entra_agent = self.get_agent("entra_groups")
                entra_config = entra_agent.generate_config(role_assignments_content)
                
                configs.append({
                    "type": "entra_groups",
                    "content": entra_config["tfvars"],
                    "filename": entra_config["tfvars_filename"]
                })
            
            # Format the combined output
            combined_output = self._format_output(configs)
            
            # Get main.tf content
            main_tf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'terraform', 'main.tf')
            main_tf_content = ""
            if os.path.exists(main_tf_path):
                try:
                    with open(main_tf_path, 'r') as f:
                        main_tf_content = f.read()
                except Exception as e:
                    st.error(f"Error reading main.tf: {str(e)}")
            
            return {
                "success": True,
                "message": f"Generated {len(configs)} Terraform configurations",
                "configs": configs,
                "combined": combined_output,
                "main_tf": main_tf_content
            }
            
        except Exception as e:
            st.error(f"Error in agent factory: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to generate Terraform configurations: {str(e)}",
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

    @staticmethod
    def create_agent(agent_type: str, templates_dir: str) -> BaseAgent:
        """
        Create a specialized agent based on the agent type.
        
        Args:
            agent_type (str): Type of agent to create
            templates_dir (str): Directory containing prompt templates
            
        Returns:
            BaseAgent: Specialized agent instance
            
        Raises:
            ValueError: If agent_type is not supported
        """
        if agent_type == "resource_group":
            return ResourceGroupAgent(templates_dir)
        elif agent_type == "storage_account":
            return StorageAccountAgent(templates_dir)
        elif agent_type == "key_vault":
            return KeyVaultAgent(templates_dir)
        else:
            raise ValueError(f"Unsupported agent type: {agent_type}") 