import os
import re
import streamlit as st
from typing import Dict, Any
from .base_agent import BaseAgent

class EntraGroupsAgent(BaseAgent):
    """Agent specialized in generating Terraform configurations for Azure Entra ID Groups based on role assignments."""
    
    def __init__(self, template_dir: str, debug_mode: bool = False):
        """Initialize the Entra groups agent."""
        super().__init__(template_dir, debug_mode)
        self.prompt_file = "entra_groups_prompt.txt"
    
    def generate_config(self, role_assignments_tfvars: str) -> Dict[str, Any]:
        """Generate Terraform configuration for Entra ID groups based on role assignments."""
        try:
            # Load the Entra groups prompt file
            system_prompt = self._load_prompt_template(self.prompt_file)
            
            # Define a local debug print function
            def debug_print(*args, **kwargs):
                if hasattr(st.session_state, 'debug_mode') and st.session_state.debug_mode:
                    st.write(*args, **kwargs)
            
            # Extract role assignments from the provided tfvars string
            groups = []
            
            # First, try to find the role_assignments block
            role_assignments_match = re.search(r'role_assignments\s*=\s*{([^}]*)}', role_assignments_tfvars, re.DOTALL)
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
                group_matches = re.finditer(group_pattern, role_assignments_tfvars, re.DOTALL)
                
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
                group_matches = re.finditer(group_pattern, role_assignments_tfvars, re.DOTALL)
                
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
                return {
                    "main_config": "",
                    "tfvars": "",
                    "tfvars_filename": "entra_groups.auto.tfvars"
                }
            
            # Create the user prompt with all role assignments
            user_prompt = "Generate Entra groups for the following role assignments:\n"
            for group_key, group_name, role in groups:
                user_prompt += f"- {group_name} ({role})\n"
            
            debug_print(f"Generated user prompt: {user_prompt}")
            
            # Generate the Entra groups configuration with the LLM
            if self.llm:
                response = self.llm.invoke(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                tfvars = response.content.strip()
                
                # Validate the response format
                if not tfvars.startswith("entra_groups"):
                    # Attempt to extract content if wrapped in markdown
                    match = re.search(r'```(?:hcl)?\s*(entra_groups.*?)\s*```', tfvars, re.DOTALL)
                    if match:
                        tfvars = match.group(1).strip()
                    else:
                        # Fall back to manually generating groups
                        debug_print("LLM response was not properly formatted, falling back to manual generation")
                        tfvars = self._generate_groups_manually(groups)
                        
            else:
                # Skip LLM call and manually generate groups if LLM is not available
                debug_print("LLM not available, generating groups manually")
                tfvars = self._generate_groups_manually(groups)
            
            # Return the configuration
            return {
                "main_config": "",  # No main.tf needed for Entra groups
                "tfvars": tfvars,
                "tfvars_filename": "entra_groups.auto.tfvars"
            }
            
        except Exception as e:
            st.error(f"Error generating Entra groups configuration: {str(e)}")
            raise Exception(f"Failed to generate Entra groups configuration: {str(e)}")
    
    def _generate_groups_manually(self, groups):
        """Generate Entra groups configuration manually based on extracted groups."""
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
        return tfvars 