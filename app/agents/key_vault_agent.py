import os
import re
import streamlit as st
from typing import Dict, Any, List, Tuple
from .base_agent import BaseAgent

class KeyVaultAgent(BaseAgent):
    """Agent specialized in generating Terraform configurations for Azure Key Vaults."""
    
    def __init__(self, templates_dir: str):
        """Initialize the key vault agent."""
        super().__init__(templates_dir)
        self.prompt_file = "key_vault_prompt.txt"
    
    def _ensure_kv_prefix(self, name: str) -> str:
        """Ensure the name starts with 'kv-' prefix."""
        if not name.startswith("kv-"):
            return f"kv-{name}"
        return name
    
    def generate_config(self, query: str) -> Dict[str, Any]:
        """
        Generate Terraform configuration for key vaults based on the query.
        
        Args:
            query (str): User's natural language query
            
        Returns:
            dict: Configuration details including main_config, tfvars, tfvars_filename, and entra_configs
        """
        # Load the key vault prompt
        system_prompt = self._load_prompt_template(self.prompt_file)
        if not system_prompt:
            return {
                "main_config": "",
                "tfvars": "# Error: Key vault prompt file not found",
                "tfvars_filename": "key_vault.auto.tfvars",
                "entra_configs": {"main_config": "", "tfvars": "", "tfvars_filename": "entra_groups.auto.tfvars"}
            }
            
        # Generate Terraform configuration
        response = self.llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]).content
        
        # Extract the main content
        match = re.search(r"```hcl\s*(.*?)```", response, re.DOTALL)
        if match:
            tf_vars = match.group(1).strip()
        else:
            tf_vars = response.strip()
        
        # Check for role assignments to generate Entra groups
        entra_configs = {"main_config": "", "tfvars": "", "tfvars_filename": "entra_groups.auto.tfvars"}
        if "role_assignments" in tf_vars and "{}" not in tf_vars:
            entra_configs = self._generate_entra_groups_config(tf_vars)
            
        return {
            "main_config": "",
            "tfvars": tf_vars,
            "tfvars_filename": "key_vault.auto.tfvars",
            "entra_configs": entra_configs
        }
        
    def _fallback_key_vault_config(self, query):
        """
        Fallback function to generate a basic key vault configuration
        based on the query if the LLM response format validation fails.
        """
        # Extract key vault name from query
        match = re.search(r"key\s+vault\s+(?:named\s+)?([a-zA-Z0-9-]+)", query, re.IGNORECASE)
        kv_name = match.group(1) if match else "kv1"
        if not kv_name.startswith("kv-"):
            kv_name = f"kv-{kv_name}"
        
        # Generate basic config
        tf_vars = f"""key_vault = {{
  {kv_name} = {{
    name               = "{kv_name}"
    resource_group_key = "rg01"

    private_endpoints = {{
      vault = {{
        subresource_name = "vault"
      }}
    }}
    network_acls        = {{}}
    diagnostic_settings = {{}}

    role_assignments = {{}}
  }}
}}"""
        
        return {
            "main_config": "",
            "tfvars": tf_vars,
            "tfvars_filename": "key_vault.auto.tfvars",
            "entra_configs": {"main_config": "", "tfvars": "", "tfvars_filename": "entra_groups.auto.tfvars"}
        }
        
    def _generate_entra_groups_config(self, key_vault_tfvars):
        """
        Generate Terraform configuration for Entra groups based on key vault role assignments.
        
        Args:
            key_vault_tfvars (str): The tfvars string containing key vaults with role assignments
            
        Returns:
            dict: Configuration details for Entra groups
        """
        # Load the Entra groups prompt
        system_prompt = self._load_prompt_template("entra_groups_prompt.txt")
        if not system_prompt:
            return {"main_config": "", "tfvars": "", "tfvars_filename": "entra_groups.auto.tfvars"}
        
        # Extract role assignments from the key_vault_tfvars
        groups = []
        seen_group_keys = set()
        
        # Pattern 1: Find role_assignments blocks
        pattern1 = r'role_assignments\s*=\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}'
        roles_blocks = re.findall(pattern1, key_vault_tfvars, re.DOTALL)
        
        for block in roles_blocks:
            # Pattern 2: Extract individual role assignments
            pattern2 = r'([a-zA-Z0-9_-]+)\s*=\s*\{\s*(?:name\s*=\s*"([^"]+)")?\s*(?:role\s*=\s*"([^"]+)")?\s*\}'
            role_matches = re.findall(pattern2, block, re.DOTALL)
            
            for role_key, role_name, role in role_matches:
                # Use role name if provided, otherwise use role key
                group_name = role_name if role_name else role_key
                
                # Skip if group key already seen (avoid duplicates)
                if role_key in seen_group_keys:
                    continue
                
                seen_group_keys.add(role_key)
                groups.append({
                    "key": role_key,
                    "name": group_name,
                    "role": role
                })
        
        # If no groups found, return empty config
        if not groups:
            return {"main_config": "", "tfvars": "", "tfvars_filename": "entra_groups.auto.tfvars"}
        
        # Create user prompt listing the role assignments
        user_prompt = "Generate Entra groups for the following role assignments:\n"
        for group in groups:
            user_prompt += f"- {group['key']}: name = \"{group['name']}\", role = \"{group['role']}\"\n"
        
        # Generate Terraform configuration
        response = self.llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]).content
        
        # Extract the main content
        match = re.search(r"```hcl\s*(.*?)```", response, re.DOTALL)
        if match:
            tf_vars = match.group(1).strip()
        else:
            tf_vars = response.strip()
            
        return {
            "main_config": "",
            "tfvars": tf_vars,
            "tfvars_filename": "entra_groups.auto.tfvars"
        }
    
    def has_role_assignments(self, config: Dict[str, Any]) -> bool:
        """Check if the key vault configuration has role assignments."""
        return "role_assignments" in config.get("tfvars", "") and "{}" not in config.get("tfvars", "") 