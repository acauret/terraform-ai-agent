import os
import shutil
import sys

def check_templates():
    """Check if the templates directory exists and contains template files."""
    # Get the directory paths
    app_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(app_dir)
    templates_dir = os.path.join(project_dir, 'templates')
    
    print(f"Checking templates directory: {templates_dir}")
    
    # Check if templates directory exists
    if not os.path.exists(templates_dir):
        print(f"Templates directory does not exist. Creating: {templates_dir}")
        os.makedirs(templates_dir, exist_ok=True)
    
    # Check if templates directory has .tf and .tfvars files
    tf_files = [f for f in os.listdir(templates_dir) if f.endswith('.tf')]
    tfvars_files = [f for f in os.listdir(templates_dir) if f.endswith('.tfvars')]
    
    print(f"Found {len(tf_files)} .tf files and {len(tfvars_files)} .tfvars files in templates directory")
    
    # If no template files are found, create sample templates
    if not tf_files and not tfvars_files:
        print("No template files found. Creating sample templates...")
        create_sample_templates(templates_dir)
        
def create_sample_templates(templates_dir):
    """Create sample template files in the templates directory."""
    # Create resource group template
    resource_group_tf = """resource "azurerm_resource_group" "this" {
  name     = var.resource_group_name
  location = var.location
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region where the resource group will be created"
  type        = string
  default     = "eastus"
}
"""
    
    resource_group_tfvars = """# Name of the resource group
resource_group_name = "my-project"

# Azure region where the resource group will be created
location = "eastus"
"""
    
    # Create storage account template
    storage_account_tf = """resource "azurerm_storage_account" "this" {
  name                     = var.storage_account_name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = var.account_tier
  account_replication_type = var.account_replication_type
  
  tags = var.tags
}

variable "storage_account_name" {
  description = "Name of the storage account"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region where the storage account will be created"
  type        = string
  default     = "eastus"
}

variable "account_tier" {
  description = "Tier of the storage account"
  type        = string
  default     = "Standard"
}

variable "account_replication_type" {
  description = "Replication type for the storage account"
  type        = string
  default     = "LRS"
}

variable "tags" {
  description = "Tags to apply to the storage account"
  type        = map(string)
  default     = {}
}
"""
    
    storage_account_tfvars = """storage_accounts = {
  st01 = {
    name                      = "mystorageaccount"
    resource_group_key        = "rg01"
    access_tier               = "Hot"
    account_kind              = "StorageV2"
    account_replication_type  = "ZRS"
    account_tier              = "Standard"
    
    private_endpoints = {
      blob = {
        subresource_name = "blob"
      }
    }
    
    container = {}
    
    role_assignments = {}
  }
}
"""
    
    # Create key vault template
    key_vault_tf = """resource "azurerm_key_vault" "this" {
  name                = var.key_vault_name
  resource_group_name = var.resource_group_name
  location            = var.location
  tenant_id           = var.tenant_id
  sku_name            = var.sku_name
  
  enabled_for_disk_encryption = var.enabled_for_disk_encryption
  purge_protection_enabled    = var.purge_protection_enabled
  
  tags = var.tags
}

variable "key_vault_name" {
  description = "Name of the key vault"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region where the key vault will be created"
  type        = string
  default     = "eastus"
}

variable "tenant_id" {
  description = "Azure AD tenant ID"
  type        = string
}

variable "sku_name" {
  description = "SKU name for the key vault"
  type        = string
  default     = "standard"
}

variable "enabled_for_disk_encryption" {
  description = "Whether the key vault is enabled for disk encryption"
  type        = bool
  default     = true
}

variable "purge_protection_enabled" {
  description = "Whether purge protection is enabled"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags to apply to the key vault"
  type        = map(string)
  default     = {}
}
"""
    
    key_vault_tfvars = """key_vault = {
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
}
"""
    
    # Create entra groups template
    entra_groups_tf = """resource "azuread_group" "this" {
  for_each = var.entra_groups
  
  display_name     = each.value.display_name
  description      = each.value.description
  security_enabled = true
  owners           = each.value.owners
}

variable "entra_groups" {
  description = "Map of Entra ID groups to create"
  type = map(object({
    display_name = string
    description  = string
    owners       = list(string)
  }))
  default = {}
}
"""
    
    entra_groups_tfvars = """entra_groups = {
  admin = {
    display_name = "admin"
    description  = "Administrator role for admin"
    owners       = ["00000000-0000-0000-0000-000000000000"]
  }
  contributor = {
    display_name = "contributor"
    description  = "Contributor role for contributor"
    owners       = ["00000000-0000-0000-0000-000000000000"]
  }
}
"""
    
    # Create prompt files
    resource_group_prompt = """You are a Terraform expert specializing in Azure Resource Groups. Your task is to generate a Terraform .tfvars file for Azure resource groups based on user requirements.

Do not include any explanations or markdown syntax in your response. The output should be a valid, ready-to-use Terraform .tfvars file.

The output should follow this exact format:

```
resource_groups = {
  # Resource group details
  <key> = {
    name     = "<name>"
    location = "<location>"
    role_assignments = {
      <role_key> = {
        resourcename           = "<resource_name>"
        role_definition_id_or_name = "<role_definition>"
        principal_id           = "<principal_id>"
      }
    }
  }
}
```

Guidelines:
1. Use meaningful, concise keys (e.g., rg01, rg-prod)
2. Extract the resource group name from the user query
3. Set a suitable Azure region based on user preferences or fallback to "eastus"
4. Include role assignments only if the user mentions roles or permissions
5. Use appropriate role definitions (e.g., "Owner", "Contributor", "Reader")
6. For principal_id, use the role name as a placeholder
7. If multiple resource groups are requested, create separate entries
8. If no location is specified, use "eastus" as default
9. Don't add any comments or explanation to the output - only provide the tfvars content
10. Don't include variable declarations - only values
11. If roles are mentioned, use the exact string from the query
12. Format the response consistently with proper spacing and indentation
13. Always put quotes around string values
14. Role assignments should correspond to the roles mentioned in the query
15. Don't include any extra variables or fields not shown in the example format

Do not include any additional variables or comments in your response beyond what's shown in the example.
"""
    
    storage_account_prompt = """You are a Terraform expert specializing in Azure Storage Accounts. Your task is to generate a Terraform .tfvars file for Azure storage accounts based on user requirements.

Do not include any explanations or markdown syntax in your response. The output should be a valid, ready-to-use Terraform .tfvars file.

The output should follow this exact format:

```
storage_accounts = {
  # Storage account details
  <key> = {
    name                      = "<name>"
    resource_group_key        = "<resource_group_key>"
    access_tier               = "<access_tier>"
    account_kind              = "<account_kind>"
    account_replication_type  = "<account_replication_type>"
    account_tier              = "<account_tier>"

    private_endpoints = {
      <endpoint_key> = {
        subresource_name = "<subresource_name>"
      }
    }
    container = {
      <container_key> = {
        name = "<container_name>"
      }
    }

    role_assignments = {
      <role_key> = {
        resourcename           = "<resource_name>"
        role_definition_id_or_name = "<role_definition>"
        principal_id           = "<principal_id>"
      }
    }
  }
}
```

Guidelines:
1. Use meaningful, concise keys (e.g., st01, st-prod)
2. Extract the storage account name from the user query
3. Set resource_group_key to "rg01" by default
4. Use appropriate values for:
   - access_tier: "Hot" or "Cool"
   - account_kind: "StorageV2", "BlobStorage", etc.
   - account_replication_type: "LRS", "GRS", "ZRS", etc.
   - account_tier: "Standard" or "Premium"
5. Include private_endpoints for blob, file, table, or queue as needed
6. Include containers if mentioned
7. Include role assignments only if the user mentions roles or permissions
8. Use appropriate role definitions (e.g., "Storage Blob Data Contributor")
9. For principal_id, use the role name as a placeholder
10. Don't add any comments or explanation to the output - only provide the tfvars content
11. Don't include variable declarations - only values
12. If roles are mentioned, use the exact string from the query
13. Format the response consistently with proper spacing and indentation
14. Always put quotes around string values
15. Role assignments should create corresponding Entra ID groups when specified

Do not include any additional variables or comments in your response beyond what's shown in the example.
"""
    
    key_vault_prompt = """You are a Terraform expert specializing in Azure Key Vault. Your task is to generate a Terraform .tfvars file for Azure Key Vault based on user requirements.

Do not include any explanations or markdown syntax in your response. The output should be a valid, ready-to-use Terraform .tfvars file.

The output should follow this exact format:

```
key_vault = {
  # Key Vault details
  <key> = {
    name               = "<name>"
    resource_group_key = "<resource_group_key>"

    private_endpoints = {
      <endpoint_key> = {
        subresource_name = "<subresource_name>"
      }
    }
    network_acls        = {}
    diagnostic_settings = {}

    role_assignments = {
      <role_key> = {
        resourcename           = "<resource_name>"
        role_definition_id_or_name = "<role_definition>"
        principal_id           = "<principal_id>"
      }
    }
  }
}
```

Guidelines:
1. Use meaningful, concise keys (e.g., kv01, kv-prod)
2. Extract the Key Vault name from the user query
3. Set resource_group_key to "rg01" by default
4. Include private_endpoints for vault if needed
5. Keep network_acls and diagnostic_settings empty if not specified
6. Include role assignments only if the user mentions roles or permissions
7. Use appropriate role definitions (e.g., "Key Vault Administrator", "Key Vault Certificates Officer")
8. For principal_id, use the role name as a placeholder
9. Don't add any comments or explanation to the output - only provide the tfvars content
10. Don't include variable declarations - only values
11. If roles are mentioned, use the exact string from the query
12. Format the response consistently with proper spacing and indentation
13. Always put quotes around string values
14. Role assignments should create corresponding Entra ID groups when specified

Do not include any additional variables or comments in your response beyond what's shown in the example.
"""
    
    entra_groups_prompt = """You are a Terraform expert specializing in Azure Entra ID groups. This prompt is triggered AFTER either a resource group or storage account with role assignments has been created.

Your task is to generate a Terraform .tfvars file for Azure Entra ID groups based on the role assignments specified in the resource group or storage account.

Do not include any explanations or markdown syntax in your response. The output should be a valid, ready-to-use Terraform .tfvars file.

The output should follow this exact format:

```
entra_groups = {
  <group_name> = {
    display_name = "<group_name>"
    description  = "<role> role for <group_name>"
    owners       = ["00000000-0000-0000-0000-000000000000"]
  }
}
```

Guidelines:
1. Use the exact group name from the role assignments block in the resource group or storage account
2. The display_name should match the group_name
3. The description should include the role and the group name
4. The owners should include a placeholder UUID
5. Don't add any comments or explanation to the output - only provide the tfvars content
6. Don't include variable declarations - only values
7. Format the response consistently with proper spacing and indentation
8. Always put quotes around string values

Example:
If a resource group has this role assignment:
```
role_assignments = {
  admin = {
    resourcename = "admin"
    role_definition_id_or_name = "Owner"
    principal_id = "admin"
  }
}
```

You should generate:
```
entra_groups = {
  admin = {
    display_name = "admin"
    description  = "Owner role for admin"
    owners       = ["00000000-0000-0000-0000-000000000000"]
  }
}
```

If a storage account has the following role assignments:
```
role_assignments = {
  reader = {
    resourcename = "reader"
    role_definition_id_or_name = "Reader"
    principal_id = "reader"
  }
  contributor = {
    resourcename = "contributor"
    role_definition_id_or_name = "Contributor"
    principal_id = "contributor"
  }
}
```

You should generate:
```
entra_groups = {
  reader = {
    display_name = "reader"
    description  = "Reader role for reader"
    owners       = ["00000000-0000-0000-0000-000000000000"]
  }
  contributor = {
    display_name = "contributor"
    description  = "Contributor role for contributor"
    owners       = ["00000000-0000-0000-0000-000000000000"]
  }
}
```

Do not include any additional variables or comments in your response beyond what's shown in the example.
"""
    
    # Write all files
    with open(os.path.join(templates_dir, 'resource_group.tf'), 'w') as f:
        f.write(resource_group_tf)
    with open(os.path.join(templates_dir, 'resource_group.tfvars'), 'w') as f:
        f.write(resource_group_tfvars)
    
    with open(os.path.join(templates_dir, 'storage_account.tf'), 'w') as f:
        f.write(storage_account_tf)
    with open(os.path.join(templates_dir, 'storage_account.tfvars'), 'w') as f:
        f.write(storage_account_tfvars)
    
    with open(os.path.join(templates_dir, 'key_vault.tf'), 'w') as f:
        f.write(key_vault_tf)
    with open(os.path.join(templates_dir, 'key_vault.tfvars'), 'w') as f:
        f.write(key_vault_tfvars)
    
    with open(os.path.join(templates_dir, 'entra_groups.tf'), 'w') as f:
        f.write(entra_groups_tf)
    with open(os.path.join(templates_dir, 'entra_groups.tfvars'), 'w') as f:
        f.write(entra_groups_tfvars)
    
    # Write prompt files
    with open(os.path.join(templates_dir, 'resource_group_prompt.txt'), 'w') as f:
        f.write(resource_group_prompt)
    with open(os.path.join(templates_dir, 'storage_account_prompt.txt'), 'w') as f:
        f.write(storage_account_prompt)
    with open(os.path.join(templates_dir, 'key_vault_prompt.txt'), 'w') as f:
        f.write(key_vault_prompt)
    with open(os.path.join(templates_dir, 'entra_groups_prompt.txt'), 'w') as f:
        f.write(entra_groups_prompt)
    
    print(f"Created sample templates in {templates_dir}")
    print("Templates created successfully!")

if __name__ == "__main__":
    check_templates() 