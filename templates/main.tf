# Create the Resource Group
module "resourcegroups" {
  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-resources-resourcegroup?ref=b4103725a300d02b8032c529dc0b24197c0a8ced" #v0.2.1
  #
  for_each = var.resource_groups

  name             = each.value.name
  location         = each.value.location
  enable_telemetry = false

  role_assignments = {
    for s in each.value.role_assignments : s.resourcename => {
      principal_id               = contains(keys(azuread_group.this), s.principal_id) ? replace(replace(azuread_group.this[s.principal_id].id, "/groups/", ""), "/", "") : s.principal_id
      role_definition_id_or_name = try(s.role_definition_id_or_name, null)
    }
  }

  lock = try(each.value.lock, null)
  #
  tags = try(each.value.tags, null)

}

# Create the necessary groups needed for RBAC
resource "azuread_group" "this" {
  for_each = var.entra_groups

  display_name            = each.value.display_name
  description             = try(each.value.description, null)
  owners                  = try(each.value.owners, [data.azuread_client_config.current.object_id])
  prevent_duplicate_names = true
  security_enabled        = true
}

# Create the Cognitive services account
module "cognitive_services" {
  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-cognitiveservices-account?ref=a73f04df4725afeea3ef0e60ef0eb7f3330f560a" #v0.7.0

  for_each = var.cognitive_services

  name                = each.value.name
  resource_group_name = module.resourcegroups[each.value.resource_group_key].resource.name
  location            = module.resourcegroups[each.value.resource_group_key].resource.location

  kind                               = try(each.value.kind, "CognitiveServices")
  sku_name                           = try(each.value.sku_name, "S0")
  local_auth_enabled                 = try(each.value.local_auth_enabled, false)
  public_network_access_enabled      = try(each.value.public_network_access_enabled, false)
  outbound_network_access_restricted = try(each.value.outbound_network_access_restricted, true)

  cognitive_deployments = contains(keys(each.value), "cognitive_deployments") ? {
    for s in each.value.cognitive_deployments : s.name => {
      name                   = try(s.name, null)
      rai_policy_name        = try(s.rai_policy_name, null)
      version_upgrade_option = try(s.version_upgrade_option, "OnceNewDefaultVersionAvailable")
      model = {
        format  = try(s.model.format, null)
        name    = try(s.model.name, null)
        version = try(s.model.version, null)
      }
      scale = {
        type     = try(s.scale.type, null)
        capacity = try(s.scale.capacity, 1)
        tier     = try(s.scale.tier, null)
        size     = try(s.scale.size, null)
        family   = try(s.scale.family, null)
      }
    }
  } : {}

  managed_identities = {
    system_assigned            = try(each.value.managed_identities.system_assigned, true)
    user_assigned_resource_ids = try(each.value.managed_identities.user_assigned_resource_ids, [])
  }

  diagnostic_settings = {
    for s in each.value.diagnostic_settings : s.name => {
      name                           = try(s.name, null)
      log_analytics_destination_type = try(s.log_analytics_destination_type, null)
      workspace_resource_id          = try(data.azurerm_log_analytics_workspace.this[each.key].id, [])
    }
  }

  private_endpoints = {
    for s in each.value.private_endpoints : s.subresource_name => {
      name                          = "pe-${each.value.name}-${s.subresource_name}"
      subresource_name              = s.subresource_name
      location                      = module.resourcegroups[each.value.resource_group_key].resource.location
      private_dns_zone_resource_ids = try([local.dns_zones[local.subresource_to_dns_zone[s.subresource_name]]], [])
      subnet_resource_id            = data.azurerm_subnet.pvt[each.key].id
      private_ip_address            = try(s.private_ip_address, null)
      #
      private_service_connection_name = "${each.value.name}-${s.subresource_name}-private-service-connection"
      network_interface_name          = "${each.value.name}-${s.subresource_name}-private-endpoint-nic"
    }
  }
  #
  lock = try(each.value.lock, null)
  #
}

# Create the KeyVault Resource
module "key_vault" {
  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-keyvault-vault?ref=2dd068bb15da0e1de890cac4cee93e945ff36973" #v0.10.0

  for_each = var.key_vault

  name                = each.value.name
  location            = module.resourcegroups[each.value.resource_group_key].resource.location
  resource_group_name = module.resourcegroups[each.value.resource_group_key].resource.name
  tenant_id           = data.azurerm_client_config.current.tenant_id

  public_network_access_enabled = try(each.value.public_network_access_enabled, false)
  purge_protection_enabled      = try(each.value.purge_protection_enabled, true)

  network_acls = {
    bypass                     = try(each.value.network_acls.bypass, "None")
    default_action             = try(each.value.network_acls.default_action, "Deny")
    ip_rules                   = try(each.value.network_acls.ip_rules, [])
    virtual_network_subnet_ids = try([for k, s in data.azurerm_subnet.this : s.id if split("-snet", k)[0] == each.key], [])
  }

  private_endpoints = {
    for s in each.value.private_endpoints : s.subresource_name => {
      name                          = "pe-${each.value.name}-${s.subresource_name}"
      subresource_name              = s.subresource_name
      location                      = module.resourcegroups[each.value.resource_group_key].resource.location
      private_dns_zone_resource_ids = try([local.dns_zones[local.subresource_to_dns_zone[s.subresource_name]]], [])
      subnet_resource_id            = data.azurerm_subnet.pvt[each.key].id
      private_ip_address            = try(s.private_ip_address, null)
      #
      private_service_connection_name = "${each.value.name}-${s.subresource_name}-private-service-connection"
      network_interface_name          = "${each.value.name}-${s.subresource_name}-private-endpoint-nic"
    }
  }

  diagnostic_settings = {
    for s in each.value.diagnostic_settings : s.name => {
      name                  = try(s.name, null)
      log_groups            = try(s.log_groups, ["allLogs"])
      workspace_resource_id = try(data.azurerm_log_analytics_workspace.this[each.key].id, [])
    }
  }

  role_assignments = {
    for s in each.value.role_assignments : s.resourcename => {
      principal_id               = contains(keys(azuread_group.this), s.principal_id) ? replace(replace(azuread_group.this[s.principal_id].id, "/groups/", ""), "/", "") : s.principal_id
      role_definition_id_or_name = try(s.role_definition_id_or_name, null)
    }
  }
  #
  lock = try(each.value.lock, null)
  #
}

# Create the Azure DataFactory resources
module "data_factory" {
  source = "git::https://github.com/SkittleBomb/terraform-azurerm-avm-res-datafactory-factory?ref=6cdb44c180d95299b08d9475706285166b52284f" #V0.13

  for_each = var.data_factory

  name                = each.value.name
  resource_group_name = module.resourcegroups[each.value.resource_group_key].resource.name
  location            = module.resourcegroups[each.value.resource_group_key].resource.location
  purview_id          = try(each.value.purview_id, null)

  public_network_enabled          = try(each.value.public_network_enabled, false)
  managed_virtual_network_enabled = try(each.value.managed_virtual_network_enabled, true)

  private_endpoints = {
    for s in each.value.private_endpoints : s.subresource_name => {
      subresource_name              = s.subresource_name
      location                      = module.resourcegroups[each.value.resource_group_key].resource.location
      private_dns_zone_resource_ids = try([local.dns_zones[local.subresource_to_dns_zone[s.subresource_name]]], [])
      subnet_resource_id            = data.azurerm_subnet.pvt[each.key].id
      #
      private_service_connection_name = "${each.value.name}-${s.subresource_name}-private-service-connection"
      network_interface_name          = "${each.value.name}-${s.subresource_name}-private-endpoint-nic"
    }
  }

  diagnostic_settings = {
    for s in each.value.diagnostic_settings : s.name => {
      name                           = try(s.name, null)
      workspace_resource_id          = try(data.azurerm_log_analytics_workspace.this[each.key].id, [])
      log_analytics_destination_type = try(s.log_analytics_destination_type, "Dedicated")
    }
  }

  github_configuration = contains(keys(each.value), "github_configuration") ? {
    account_name       = each.value.github_configuration.account_name
    branch_name        = each.value.github_configuration.branch_name
    git_url            = each.value.github_configuration.git_url
    repository_name    = each.value.github_configuration.repository_name
    root_folder        = each.value.github_configuration.root_folder
    publishing_enabled = try(each.value.github_configuration.publishing_enabled, false)
  } : null

  identity = {
    type         = try(each.value.identity.type, "SystemAssigned")
    identity_ids = try(each.value.identity.identity_ids, [])
  }

  data_factory_credentials = contains(keys(each.value), "data_factory_credentials") ? {
    for m in each.value.data_factory_credentials : m.user_assigned_identity_name => {
      user_assigned_identity_name = try(m.user_assigned_identity_name, null)
      credential_description      = try(m.credential_description, null)
      user_assigned_identity_id   = try(m.user_assigned_identity_id, null)
      credential_annotations      = try(m.credential_annotations, [])
    }
  } : {}

  role_assignments = {
    for s in each.value.role_assignments : s.resourcename => {
      principal_id               = contains(keys(azuread_group.this), s.principal_id) ? replace(replace(azuread_group.this[s.principal_id].id, "/groups/", ""), "/", "") : s.principal_id
      role_definition_id_or_name = try(s.role_definition_id_or_name, null)
    }
  }

  integration_runtime_azure = contains(keys(each.value), "integration_runtime_azure") ? {
    for m in each.value.integration_runtime_azure : m.name => {
      name                    = try(m.name, null)
      location                = module.resourcegroups[each.value.resource_group_key].resource.location
      description             = try(m.description, null)
      virtual_network_enabled = try(m.virtual_network_enabled, true)
    }
  } : {}

  managed_private_endpoint = contains(keys(each.value), "managed_private_endpoint") ? {
    for m in each.value.managed_private_endpoint : m.name => {
      name               = try(m.name, null)
      target_resource_id = try(m.target_resource_id, null)
      subresource_name   = try(m.subresource_name, null)
    }
  } : {}

  linked_service_azure_databricks = {
    for d in each.value.linked_service_azure_databricks : d.name => {
      name                       = try(d.name, null)
      integration_runtime_name   = try(d.integration_runtime_name, null)
      description                = try(d.description, null)
      adb_domain                 = try(d.adb_domain, null)
      msi_work_space_resource_id = try(d.msi_work_space_resource_id, null)
      new_cluster_config = {
        node_type       = try(d.new_cluster_config.node_type, null)
        cluster_version = try(d.new_cluster_config.cluster_version, null)
      }
    }
  }

  linked_service_data_lake_storage_gen2 = {
    for d in each.value.linked_service_data_lake_storage_gen2 : d.name => {
      name                     = try(d.name, null)
      integration_runtime_name = try(d.integration_runtime_name, null)
      description              = try(d.description, null)
      url                      = try(module.storage_account[d.storageaccountname].resource.primary_dfs_endpoint, try(d.url, null))
      use_managed_identity     = true
    }
  }

  linked_service_azure_sql_database = {
    for d in each.value.linked_service_azure_sql_database : d.name => {
      name                 = try(d.name, null)
      connection_string    = "Data Source=tcp:${d.sqlservername}.database.windows.net,1433;Initial Catalog=${d.databasename};Connection Timeout=30"
      use_managed_identity = true
    }
  }

  linked_service_key_vault = {
    for d in each.value.linked_service_key_vault : d.name => {
      name         = try(d.name, null)
      description  = try(d.description, null)
      key_vault_id = module.key_vault[d.keyvaultname].resource_id
    }
  }

  linked_custom_service = {
    for d in each.value.linked_custom_service : d.name => {
      name        = try(d.name, null)
      description = try(d.description, null)
      annotations = try(d.annotations, [])
      type        = try(d.type, null)
      parameters  = lookup(d, "parameters", {})
      type_properties_json = jsonencode(merge(
        lookup(d.type_properties_json, "authenticationType", null) != null ? { authenticationType = d.type_properties_json.authenticationType } : {},
        lookup(d.type_properties_json, "url", null) != null ? { url = d.type_properties_json.url } : {},
        lookup(d.type_properties_json, "baseUrl", null) != null ? { baseUrl = d.type_properties_json.baseUrl } : {},
        lookup(d.type_properties_json, "domain", null) != null ? { domain = d.type_properties_json.domain } : {},
        lookup(d.type_properties_json, "workspaceResourceId", null) != null ? { workspaceResourceId = d.type_properties_json.workspaceResourceId } : {},
        lookup(d.type_properties_json, "newClusterNodeType", null) != null ? { newClusterNodeType = d.type_properties_json.newClusterNodeType } : {},
        lookup(d.type_properties_json, "newClusterNumOfWorker", null) != null ? { newClusterNumOfWorker = d.type_properties_json.newClusterNumOfWorker } : {},
        lookup(d.type_properties_json, "newClusterVersion", null) != null ? { newClusterVersion = d.type_properties_json.newClusterVersion } : {},
        lookup(d.type_properties_json, "clusterOption", null) != null ? { clusterOption = d.type_properties_json.clusterOption } : {},
        lookup(d.type_properties_json, "newClusterInitScripts", null) != null ? { newClusterInitScripts = d.type_properties_json.newClusterInitScripts } : {},
        lookup(d.type_properties_json, "enableServerCertificateValidation", null) != null ? { enableServerCertificateValidation = d.type_properties_json.enableServerCertificateValidation } : {},
        lookup(d.type_properties_json, "userName", null) != null ? { userName = d.type_properties_json.userName } : {},
        lookup(d.type_properties_json, "connectionString", null) != null ? { connectionString = d.type_properties_json.connectionString } : {},
        lookup(d.type_properties_json, "password", null) != null ? { password = {
          type       = try(d.type_properties_json.password.type, "")
          secretName = try(d.type_properties_json.password.secretName, null)
          store = lookup(d.type_properties_json.password, "store", null) != null ? {
            referenceName = try(d.type_properties_json.password.store.referenceName, null)
            type          = try(d.type_properties_json.password.store.type, null)
          } : {}
        } } : {},
        lookup(d.type_properties_json, "credential", null) != null ? { credential = {
          type          = try(d.type_properties_json.credential.type, "")
          referenceName = try(d.type_properties_json.credential.referenceName, null)
        } } : {},
        lookup(d.type_properties_json, "accountKey", null) != null ? { accountKey = {
          type       = try(d.type_properties_json.accountKey.type, "")
          secretName = try(d.type_properties_json.accountKey.secretName, null)
          store = lookup(d.type_properties_json.accountKey, "store", null) != null ? {
            referenceName = try(d.type_properties_json.accountKey.store.referenceName, null)
            type          = try(d.type_properties_json.accountKey.store.type, null)
          } : {}
        } } : {}
      ))
      integration_runtime = try(d.integration_runtime, null)
    }
  }
  #
  lock = try(each.value.lock, null)
  #
}

module "res-service-plan" {
  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-web-serverfarm?ref=146bbb25655a90d915a9ae54d37bb0c5527b55ea" #V0.4.0

  # insert the 4 required variables here
  for_each = var.service_plans

  name                         = each.value.name
  resource_group_name          = module.resourcegroups[each.value.resource_group_key].resource.name
  location                     = module.resourcegroups[each.value.resource_group_key].resource.location
  os_type                      = try(each.value.os_type, "Windows")
  sku_name                     = try(each.value.sku_name, "WS1")
  zone_balancing_enabled       = try(each.value.zone_balancing_enabled, false)
  worker_count                 = try(each.value.worker_count, 1)
  maximum_elastic_worker_count = try(each.value.maximum_elastic_worker_count, 2)
  per_site_scaling_enabled     = try(each.value.per_site_scaling_enabled, false)

  role_assignments = {
    for s in each.value.role_assignments : s.resourcename => {
      principal_id               = contains(keys(azuread_group.this), s.principal_id) ? replace(replace(azuread_group.this[s.principal_id].id, "/groups/", ""), "/", "") : s.principal_id
      role_definition_id_or_name = try(s.role_definition_id_or_name, null)
    }
  }

}

# Create the Storage Account
module "storage_account" {
  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-storage-storageaccount?ref=622ae04c19305d0b2efdfb745a5ab5659e686dd0" # v0.5.0

  for_each = var.storage_accounts

  name                = each.value.name
  resource_group_name = module.resourcegroups[each.value.resource_group_key].resource.name
  location            = module.resourcegroups[each.value.resource_group_key].resource.location

  account_replication_type          = try(each.value.account_replication_type, "GRS")
  account_tier                      = try(each.value.account_tier, "Standard")
  account_kind                      = try(each.value.account_kind, "StorageV2")
  infrastructure_encryption_enabled = try(each.value.infrastructure_encryption_enabled, false)
  shared_access_key_enabled         = try(each.value.shared_access_key_enabled, false)
  public_network_access_enabled     = try(each.value.public_network_access_enabled, false)
  is_hns_enabled                    = try(each.value.is_hns_enabled, false)
  sftp_enabled                      = try(each.value.sftp_enabled, false)
  default_to_oauth_authentication   = try(each.value.default_to_oauth_authentication, true)
  network_rules = merge({
    bypass                     = try(each.value.network_rules.bypass, ["AzureServices"])
    default_action             = try(each.value.network_rules.default_action, "Deny")
    ip_rules                   = try(each.value.network_rules.ip_rules, [])
    virtual_network_subnet_ids = try([for k, s in data.azurerm_subnet.this : s.id if split("-snet", k)[0] == each.key], [])
    }, try({
      private_link_access = [for access in each.value.network_rules.private_link_access : {
        endpoint_tenant_id   = try(access.endpoint_tenant_id, null)
        endpoint_resource_id = access.endpoint_resource_id
      }]
  }, {}))

  diagnostic_settings_blob = {
    for s in try(each.value.diagnostic_settings_blob, [
      {
        name              = "diag-${each.value.name}"
        log_groups        = ["allLogs"]
        log_categories    = ["audit", "alllogs"]
        metric_categories = ["Capacity", "Transaction"]
      }
      ]) : s.name => {
      name                  = try(s.name, "diag-${each.value.name}")
      log_groups            = try(s.log_groups, ["allLogs"])
      log_categories        = try(s.log_categories, [])
      metric_categories     = try(s.metric_categories, ["AllMetrics"])
      workspace_resource_id = try(data.azurerm_log_analytics_workspace.this[each.key].id, null)
    }
  }

  diagnostic_settings_file = {
    for s in try(each.value.diagnostic_settings_file, [
      {
        name              = "diag-${each.value.name}"
        log_groups        = ["allLogs"]
        log_categories    = ["audit", "alllogs"]
        metric_categories = ["Capacity", "Transaction"]
      }
      ]) : s.name => {
      name                  = try(s.name, "diag-${each.value.name}")
      log_groups            = try(s.log_groups, ["allLogs"])
      log_categories        = try(s.log_categories, [])
      metric_categories     = try(s.metric_categories, ["AllMetrics"])
      workspace_resource_id = try(data.azurerm_log_analytics_workspace.this[each.key].id, null)
    }
  }

  diagnostic_settings_queue = {
    for s in try(each.value.diagnostic_settings_queue, [
      {
        name              = "diag-${each.value.name}"
        log_groups        = ["allLogs"]
        log_categories    = ["audit", "alllogs"]
        metric_categories = ["Capacity", "Transaction"]
      }
      ]) : s.name => {
      name                  = try(s.name, "diag-${each.value.name}")
      log_groups            = try(s.log_groups, ["allLogs"])
      log_categories        = try(s.log_categories, [])
      metric_categories     = try(s.metric_categories, ["AllMetrics"])
      workspace_resource_id = try(data.azurerm_log_analytics_workspace.this[each.key].id, null)
    }
  }

  diagnostic_settings_table = {
    for s in try(each.value.diagnostic_settings_table, [
      {
        name              = "diag-${each.value.name}"
        log_groups        = ["allLogs"]
        log_categories    = ["audit", "alllogs"]
        metric_categories = ["Capacity", "Transaction"]
      }
      ]) : s.name => {
      name                  = try(s.name, "diag-${each.value.name}")
      log_groups            = try(s.log_groups, ["allLogs"])
      log_categories        = try(s.log_categories, [])
      metric_categories     = try(s.metric_categories, ["AllMetrics"])
      workspace_resource_id = try(data.azurerm_log_analytics_workspace.this[each.key].id, null)
    }
  }

  diagnostic_settings_storage_account = {
    for s in try(each.value.diagnostic_settings_storage_account, [
      {
        name              = "diag-${each.value.name}"
        log_groups        = ["allLogs"]
        log_categories    = []
        metric_categories = ["Capacity", "Transaction"]
      }
      ]) : s.name => {
      name                  = try(s.name, "diag-${each.value.name}")
      log_groups            = try(s.log_groups, ["allLogs"])
      log_categories        = try(s.log_categories, [])
      metric_categories     = try(s.metric_categories, ["AllMetrics"])
      workspace_resource_id = try(data.azurerm_log_analytics_workspace.this[each.key].id, null)
    }
  }

  containers = contains(keys(each.value), "container") ? {
    for s in each.value.container : s.name => {
      name          = try(s.name, null)
      public_access = try(s.public_access, "None")
      metadata      = try(s.metadata, {})
      role_assignments = contains(keys(s), "role_assignments") ? {
        for r in s.role_assignments : r.resourcename => {
          principal_id               = contains(keys(azuread_group.this), r.principal_id) ? replace(replace(azuread_group.this[r.principal_id].id, "/groups/", ""), "/", "") : r.principal_id
          role_definition_id_or_name = try(r.role_definition_id_or_name, null)
        }
      } : {}
    }
  } : {}

  private_endpoints = {
    for s in each.value.private_endpoints : s.subresource_name => {
      name                            = try(s.name, "${each.value.name}-${s.subresource_name}-${"private-endpoint"}")
      private_service_connection_name = try(s.private_service_connection_name, "${each.value.name}-${s.subresource_name}-${"private-service-connection"}")
      network_interface_name          = try(s.network_interface_name, "${each.value.name}-${s.subresource_name}-${"private-endpoint-nic"}")
      subresource_name                = s.subresource_name
      private_dns_zone_resource_ids   = try([local.dns_zones[local.subresource_to_dns_zone[s.subresource_name]]], [])
      subnet_resource_id              = data.azurerm_subnet.pvt[each.key].id
    }
  }

  managed_identities = {
    system_assigned            = try(each.value.managed_identities.system_assigned, true)
    user_assigned_resource_ids = try(each.value.managed_identities.user_assigned_resource_ids, [])
  }

  queue_properties = {
    logging = {
      delete                = try(each.value.queue_properties.logging.delete, true)
      read                  = try(each.value.queue_properties.logging.read, true)
      write                 = try(each.value.queue_properties.logging.write, true)
      version               = try(each.value.queue_properties.logging.version, "1.0")
      retention_policy_days = try(each.value.queue_properties.logging.retention_policy_days, 10)
    }
  }

  role_assignments = {
    for s in each.value.role_assignments : s.resourcename => {
      principal_id               = contains(keys(azuread_group.this), s.principal_id) ? replace(replace(azuread_group.this[s.principal_id].id, "/groups/", ""), "/", "") : s.principal_id
      role_definition_id_or_name = try(s.role_definition_id_or_name, null)
    }
  }
  #
  lock = try(each.value.lock, null)
  #
}

module "virtual_machines" {

  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-compute-virtualmachine?ref=c47eeb60116a6bd7a4073f96d6239f355e661f8e" #v0.18.1

  for_each = var.virtual_machines

  name                               = each.value.name
  admin_username                     = each.value.admin_username
  allow_extension_operations         = try(each.value.allow_extension_operations, false)
  enable_telemetry                   = try(each.value.enable_telemetry, false)
  encryption_at_host_enabled         = try(each.value.encryption_at_host_enabled, true)
  generate_admin_password_or_ssh_key = try(each.value.generate_admin_password_or_ssh_key, true)
  resource_group_name                = module.resourcegroups[each.value.resource_group_key].resource.name
  location                           = module.resourcegroups[each.value.resource_group_key].resource.location
  #
  os_type  = each.value.os_type
  sku_size = each.value.sku_size
  zone     = each.value.zone

  managed_identities = {
    system_assigned            = try(each.value.managed_identities.system_assigned, true)
    user_assigned_resource_ids = try(each.value.managed_identities.user_assigned_resource_ids, [])
  }

  network_interfaces = {
    for s in each.value.network_interfaces : s.name => {
      name                           = s.name
      accelerated_networking_enabled = try(s.accelerated_networking_enabled, true)
      ip_forwarding_enabled          = try(s.ip_forwarding_enabled, false)
      ip_configurations = {
        for r in s.ip_configurations : r.name => {
          name                          = s.name
          private_ip_subnet_resource_id = data.azurerm_subnet.pvt[each.key].id
        }
      }
    }
  }

  os_disk = {
    name                 = try(each.value.os_disk.name, null)
    caching              = each.value.os_disk.caching
    storage_account_type = each.value.os_disk.storage_account_type
  }

  role_assignments = {
    for s in each.value.role_assignments : s.resourcename => {
      principal_id               = contains(keys(azuread_group.this), s.principal_id) ? replace(replace(azuread_group.this[s.principal_id].id, "/groups/", ""), "/", "") : s.principal_id
      role_definition_id_or_name = try(s.role_definition_id_or_name, null)
    }
  }

  source_image_reference = {
    publisher = each.value.source_image_reference.publisher
    offer     = each.value.source_image_reference.offer
    sku       = each.value.source_image_reference.sku
    version   = try(each.value.source_image_reference.version, "latest")

  }

  diagnostic_settings = {
    for s in each.value.diagnostic_settings : s.name => {
      name                  = try(s.name, null)
      workspace_resource_id = try(data.azurerm_log_analytics_workspace.this[each.key].id, [])
    }
  }

  tags = try(each.value.tags, null)
  #
  lock = try(each.value.lock, null)
  #

}

# Create the Container Registry
module "container_registry" {
  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-containerregistry-registry?ref=54b37934de469901953ec26ac1fe635c4b356233" #v0.4.0
  #
  for_each = var.container_registry

  name                          = each.value.name
  resource_group_name           = module.resourcegroups[each.value.resource_group_key].resource.name
  location                      = module.resourcegroups[each.value.resource_group_key].resource.location
  public_network_access_enabled = try(each.value.public_network_access_enabled, false)
  export_policy_enabled         = try(each.value.export_policy_enabled, false)
  enable_trust_policy           = try(each.value.enable_trust_policy, false)
  admin_enabled                 = try(each.value.admin_enabled, false)
  anonymous_pull_enabled        = try(each.value.anonymous_pull_enabled, false)
  data_endpoint_enabled         = try(each.value.data_endpoint_enabled, false)
  network_rule_bypass_option    = try(each.value.network_rule_bypass_option, "None")
  quarantine_policy_enabled     = try(each.value.quarantine_policy_enabled, true)
  #
  private_endpoints = {
    for s in each.value.private_endpoints : s.subresource_name => {
      subresource_name              = s.subresource_name
      private_dns_zone_resource_ids = try([local.dns_zones[local.subresource_to_dns_zone[s.subresource_name]]], [])
      subnet_resource_id            = data.azurerm_subnet.pvt[each.key].id
    }
  }
  #
  managed_identities = {
    system_assigned            = try(each.value.managed_identities.system_assigned, true)
    user_assigned_resource_ids = try(each.value.managed_identities.user_assigned_resource_ids, [])
  }
  #
  diagnostic_settings = {
    for s in each.value.diagnostic_settings : s.name => {
      name                           = try(s.name, null)
      workspace_resource_id          = try(data.azurerm_log_analytics_workspace.this[each.key].id, [])
      log_analytics_destination_type = try(s.log_analytics_destination_type, "Dedicated")
    }
  }
  #
  role_assignments = {
    for s in each.value.role_assignments : s.resourcename => {
      principal_id               = contains(keys(azuread_group.this), s.principal_id) ? replace(replace(azuread_group.this[s.principal_id].id, "/groups/", ""), "/", "") : s.principal_id
      role_definition_id_or_name = try(s.role_definition_id_or_name, null)
    }
  }
  #
  lock = try(each.value.lock, null)
  #
  tags = try(each.value.tags, null)
}

module "managed_app_environment" {
  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-app-managedenvironment?ref=9d77ff05279b4d0e02da50c8b9e6fad10ef7b204" #V0.2.1

  #
  for_each = var.managed_app_environment
  #
  name                = each.value.name
  resource_group_name = module.resourcegroups[each.value.resource_group_key].resource.name
  location            = module.resourcegroups[each.value.resource_group_key].resource.location
  #
  zone_redundancy_enabled                    = try(each.value.zone_redundancy_enabled, false)
  log_analytics_workspace_customer_id        = null
  log_analytics_workspace_primary_shared_key = null
  log_analytics_workspace_destination        = try(each.value.log_analytics_workspace_destination, "azure-monitor")
  infrastructure_resource_group_name         = try(each.value.infrastructure_resource_group_name, null)
  infrastructure_subnet_id                   = try(data.azurerm_subnet.norm[each.key].id, null)
  internal_load_balancer_enabled             = try(each.value.internal_load_balancer_enabled, false)
  #
  workload_profile = [
    for wp in each.value.workload_profile : {
      name                  = try(wp.name, "Consumption")
      workload_profile_type = try(wp.workload_profile_type, "Consumption")
      maximum_count         = try(wp.maximum_count, null)
      minimum_count         = try(wp.minimum_count, null)
    }
  ]
  #
  diagnostic_settings = {
    for s in each.value.diagnostic_settings : s.name => {
      name                           = try(s.name, null)
      workspace_resource_id          = try(data.azurerm_log_analytics_workspace.this[each.key].id, [])
      log_analytics_destination_type = try(s.log_analytics_destination_type, "Dedicated")
    }
  }
  #
  lock = try(each.value.lock, null)
  #
  depends_on = [module.resourcegroups.this]
}

module "container_app" {
  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-app-containerapp?ref=c56e33b39753a0816826ed8763c240ccb60e0992" #v0.4.0

  for_each = var.container_apps

  name                                  = each.value.name
  resource_group_name                   = module.resourcegroups[each.value.resource_group_key].resource.name
  container_app_environment_resource_id = module.managed_app_environment[each.value.managed_app_environment_name].id
  revision_mode                         = try(each.value.revision_mode, "Single")

  registries   = try(each.value.registries, [])
  secrets      = try(each.value.secrets, {})
  ingress      = try(each.value.ingress, {})
  auth_configs = try(each.value.auth_configs, {})
  template = {
    revision_suffix = try(each.value.template.revision_suffix, null)
    max_replicas    = try(each.value.template.max_replicas, null)
    min_replicas    = try(each.value.template.min_replicas, null)

    scale = {
      azure_queue_scale_rule = try(each.value.template.azure_queue_scale_rules[0], null)
      custom_scale_rule      = try(each.value.template.custom_scale_rules[0], null)
      http_scale_rule        = try(each.value.template.http_scale_rules[0], null)
      tcp_scale_rule         = try(each.value.template.tcp_scale_rules[0], null)
    }

    containers = [
      for container in each.value.template.containers : {
        name    = container.name
        image   = container.image
        cpu     = container.cpu
        memory  = container.memory
        command = try(container.command, [])
        args    = try(container.args, [])
        env     = try(container.env, [])

        liveness_probe  = try(container.liveness_probes[0], null)
        readiness_probe = try(container.readiness_probes[0], null)
        startup_probe   = try(container.startup_probes[0], null)
        volume_mounts   = try(container.volume_mounts, [])
      }
    ]

    init_containers = [
      for init_container in try(each.value.template.init_containers, []) : {
        name          = init_container.name
        image         = init_container.image
        cpu           = try(init_container.cpu, null)
        memory        = try(init_container.memory, null)
        command       = try(init_container.command, [])
        args          = try(init_container.args, [])
        env           = try(init_container.env, [])
        volume_mounts = try(init_container.volume_mounts, [])
      }
    ]

    volumes = try(each.value.template.volumes, [])
  }
  #
  managed_identities = {
    system_assigned            = try(each.value.managed_identities.system_assigned, true)
    user_assigned_resource_ids = try(each.value.managed_identities.user_assigned_resource_ids, [])
  }
  #
  role_assignments = {
    for s in each.value.role_assignments : s.resourcename => {
      principal_id               = contains(keys(azuread_group.this), s.principal_id) ? replace(replace(azuread_group.this[s.principal_id].id, "/groups/", ""), "/", "") : s.principal_id
      role_definition_id_or_name = try(s.role_definition_id_or_name, null)
    }
  }
}

resource "random_password" "adminpassword" {
  length           = 16
  override_special = "_%@"
  special          = true
}

# dbforpostgresql-flexibleserver
module "postgresql" {
  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-dbforpostgresql-flexibleserver?ref=8127c6b357fb9a33fd4fb82ed14f296342331f37" #v0.1.4
  #
  for_each = var.postgresql
  #
  name                = each.value.name
  resource_group_name = module.resourcegroups[each.value.resource_group_key].resource.name
  location            = module.resourcegroups[each.value.resource_group_key].resource.location
  #
  enable_telemetry = try(each.value.enable_telemetry, false)
  #
  public_network_access_enabled = try(each.value.public_network_access_enabled, false)
  administrator_login           = try(each.value.administrator_login, "pgadmin")
  administrator_password        = random_password.adminpassword.result
  server_version                = try(each.value.server_version, 16)
  sku_name                      = try(each.value.sku_name, "B_Standard_B1ms")
  zone                          = try(each.value.zone, 1)
  high_availability = {
    mode                      = try(each.value.high_availability.mode, "ZoneRedundant")
    standby_availability_zone = try(each.value.high_availability.standby_availability_zone, 2)
  }
  delegated_subnet_id = try(each.value.delegated_subnet_id, null)
  private_dns_zone_id = try(each.value.private_dns_zone_id, null)
  auto_grow_enabled   = try(each.value.auto_grow_enabled, false)
  #
  authentication = {
    active_directory_auth_enabled = try(each.value.authentication.active_directory_auth_enabled, true)
    password_auth_enabled         = try(each.value.authentication.password_auth_enabled, false)
    tenant_id                     = try(each.value.authentication.tenant_id, null)
  }
  #
  private_endpoints = {
    for s in each.value.private_endpoints : s.subresource_name => {
      subresource_name              = s.subresource_name
      private_dns_zone_resource_ids = try([local.dns_zones[local.subresource_to_dns_zone[s.subresource_name]]], [])
      subnet_resource_id            = data.azurerm_subnet.pvt[each.key].id
    }
  }
  #
  managed_identities = {
    system_assigned            = try(each.value.managed_identities.system_assigned, true)
    user_assigned_resource_ids = try(each.value.managed_identities.user_assigned_resource_ids, [])
  }
  #
  diagnostic_settings = {
    for s in each.value.diagnostic_settings : s.name => {
      name                           = try(s.name, null)
      workspace_resource_id          = try(data.azurerm_log_analytics_workspace.this[each.key].id, [])
      log_analytics_destination_type = try(s.log_analytics_destination_type, "Dedicated")
    }
  }
  #
  lock = try(each.value.lock, null)
  #
  tags = try(each.value.tags, null)
}

# Azure Search
module "searchservice" {
  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-search-searchservice?ref=995f2903d3628f5d42f12b333a07bbbc0d24e106" #v0.1.5
  #
  for_each = var.searchservice
  #
  name                          = each.value.name
  resource_group_name           = module.resourcegroups[each.value.resource_group_key].resource.name
  location                      = module.resourcegroups[each.value.resource_group_key].resource.location
  enable_telemetry              = try(each.value.enable_telemetry, true)
  public_network_access_enabled = try(each.value.public_network_access_enabled, false)
  local_authentication_enabled  = try(each.value.local_authentication_enabled, false)
  authentication_failure_mode   = try(each.value.authentication_failure_mode, null)
  partition_count               = try(each.value.partition_count, 1)
  replica_count                 = try(each.value.replica_count, 1)
  sku                           = try(each.value.sku, "standard")
  semantic_search_sku           = try(each.value.semantic_search_sku, "standard")
  #
  diagnostic_settings = {
    for s in each.value.diagnostic_settings : s.name => {
      name                           = try(s.name, null)
      workspace_resource_id          = try(data.azurerm_log_analytics_workspace.this[each.key].id, [])
      log_analytics_destination_type = try(s.log_analytics_destination_type, "Dedicated")
    }
  }
  #
  private_endpoints = {
    for s in each.value.private_endpoints : s.subresource_name => {
      subresource_name                = s.subresource_name
      private_dns_zone_resource_ids   = try([local.dns_zones[local.subresource_to_dns_zone[s.subresource_name]]], [])
      subnet_resource_id              = data.azurerm_subnet.pvt[each.key].id
      private_service_connection_name = "${each.value.name}-${s.subresource_name}-private-service-connection"
      network_interface_name          = "${each.value.name}-${s.subresource_name}-private-endpoint-nic"
    }
  }
  #
  # managed_identities = {
  #   system_assigned            = try(each.value.managed_identities.system_assigned, true)
  #   user_assigned_resource_ids = try(each.value.managed_identities.user_assigned_resource_ids, [])
  # }
  #
  role_assignments = {
    for s in each.value.role_assignments : s.resourcename => {
      principal_id               = contains(keys(azuread_group.this), s.principal_id) ? replace(replace(azuread_group.this[s.principal_id].id, "/groups/", ""), "/", "") : s.principal_id
      role_definition_id_or_name = try(s.role_definition_id_or_name, null)
    }
  }
  #
  lock = try(each.value.lock, null)
}

# Create the Databricks resource
module "databricks" {
  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-databricks-workspace?ref=78b68931efd5c361800ad0c17d81ebcc0038a5d2" #v0.2.0

  for_each = var.databricks

  name                                  = each.value.name
  resource_group_name                   = module.resourcegroups[each.value.resource_group_key].resource.name
  location                              = module.resourcegroups[each.value.resource_group_key].resource.location
  sku                                   = "premium"
  public_network_access_enabled         = each.value.public_network_access_enabled
  network_security_group_rules_required = each.value.network_security_group_rules_required

  custom_parameters = {
    no_public_ip                                         = true
    public_subnet_name                                   = data.azurerm_subnet.databrickspublic[each.key].name
    public_subnet_network_security_group_association_id  = data.azurerm_subnet.databrickspublic[each.key].id
    private_subnet_name                                  = data.azurerm_subnet.databricksprivate[each.key].name
    private_subnet_network_security_group_association_id = data.azurerm_subnet.databricksprivate[each.key].id
    virtual_network_id                                   = data.azurerm_virtual_network.this[each.key].id
  }

  private_endpoints = {
    for s in each.value.private_endpoints : s.subresource_name => {
      name                          = "pe-${each.value.name}-${s.subresource_name}"
      subresource_name              = s.subresource_name
      location                      = module.resourcegroups[each.value.resource_group_key].resource.location
      private_dns_zone_resource_ids = try([local.dns_zones[local.subresource_to_dns_zone[s.subresource_name]]], [])
      subnet_resource_id            = data.azurerm_subnet.pvt[each.key].id
      private_ip_address            = try(s.private_ip_address, null)
      #
      private_service_connection_name = "${each.value.name}-${s.subresource_name}-private-service-connection"
      network_interface_name          = "${each.value.name}-${s.subresource_name}-private-endpoint-nic"
    }
  }

  access_connector = {
    for s in each.value.access_connector : s.name => {
      name     = try(s.name, null)
      location = module.resourcegroups[each.value.resource_group_key].resource.location
      identity = {
        type = try(s.identity.type, null)
      }
    }
  }

  diagnostic_settings = {
    for s in each.value.diagnostic_settings : s.name => {
      name                  = try(s.name, null)
      workspace_resource_id = try(data.azurerm_log_analytics_workspace.this[each.key].id, [])
    }
  }

  role_assignments = {
    for s in each.value.role_assignments : s.resourcename => {
      principal_id               = contains(keys(azuread_group.this), s.principal_id) ? replace(replace(azuread_group.this[s.principal_id].id, "/groups/", ""), "/", "") : s.principal_id
      role_definition_id_or_name = try(s.role_definition_id_or_name, null)
    }
  }
  #
  lock = try(each.value.lock, null)
  #
  depends_on = [module.resourcegroups.this]
}

# Create the SQL Server | Database resources
module "sql_server" {
  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-sql-server.git?ref=5a3b87da2e9ba8c7b302ba5a4b55543fa5d08d37" # version 0.1.3

  for_each = var.sql_server

  name                          = each.value.sqlserver_name
  resource_group_name           = module.resourcegroups[each.value.resource_group_key].resource.name
  location                      = module.resourcegroups[each.value.resource_group_key].resource.location
  server_version                = try(each.value.server_version, "12.0")
  public_network_access_enabled = each.value.public_network_access_enabled
  administrator_login           = try(each.value.administrator_login, "${each.value.sqlserver_name}-admin")
  administrator_login_password  = random_password.adminpassword.result

  azuread_administrator = {
    login_username              = azuread_group.this[each.value.sqlserver_name].display_name
    object_id                   = replace(replace(azuread_group.this[each.value.sqlserver_name].id, "/groups/", ""), "/", "")
    azuread_authentication_only = true
  }
  #
  private_endpoints = {
    for s in each.value.private_endpoints : s.subresource_name => {
      subresource_name              = s.subresource_name
      private_dns_zone_resource_ids = try([local.dns_zones[local.subresource_to_dns_zone[s.subresource_name]]], [])
      subnet_resource_id            = data.azurerm_subnet.pvt[each.key].id
      #
      private_service_connection_name = "${each.value.sqlserver_name}-${s.subresource_name}-private-service-connection"
      network_interface_name          = "${each.value.sqlserver_name}-${s.subresource_name}-private-endpoint-nic"
    }
  }

  diagnostic_settings = {
    for server in keys(var.sql_server) : server => {
      name                                     = "${each.value.sqlserver_name}-DiagnosticSettings"
      workspace_resource_id                    = try(data.azurerm_log_analytics_workspace.this[each.key].id, [])
      log_categories                           = []
      log_groups                               = []
      metric_categories                        = ["AllMetrics"]
      storage_account_resource_id              = null
      event_hub_authorization_rule_resource_id = null
      event_hub_name                           = null
      marketplace_partner_resource_id          = null
    }
  }

  # Database creation
  databases = {
    for s in each.value.databases : s.name => {
      name                        = try(s.name, null)
      create_mode                 = try(s.create_mode, "Default")
      auto_pause_delay_in_minutes = try(s.auto_pause_delay_in_minutes, null)
      ledger_enabled              = try(s.ledger_enabled, true)
      collation                   = try(s.collation, "SQL_Latin1_General_CP1_CI_AS")
      license_type                = try(s.license_type, null)
      sku_name                    = try(s.sku_name, "S0")
      storage_account_type        = try(s.storage_account_type, "Geo")
      zone_redundant              = try(s.zone_redundant, false)
    }
  }
}

# Logic Apps | Function Apps | Websites
module "azurerm-avm-res-web-site" {
  source = "git::https://github.com/Azure/terraform-azurerm-avm-res-web-site.git?ref=0a8e622fc5d10965a0aa8403a569e9e62d099e38" #v0.16.0

  for_each = var.websites

  name                        = each.value.name
  resource_group_name         = module.resourcegroups[each.value.resource_group_key].resource.name
  location                    = module.resourcegroups[each.value.resource_group_key].resource.location
  os_type                     = try(each.value.os_type, "Windows")
  kind                        = try(each.value.kind, null)
  enable_application_insights = try(each.value.enable_application_insights, false)
  service_plan_resource_id    = module.res-service-plan[each.value.app_service_plan_key].resource.id
  storage_account_name        = module.storage_account[each.value.storage_account_key].resource.name
  storage_account_access_key  = module.storage_account[each.value.storage_account_key].resource.primary_access_key
  virtual_network_subnet_id   = try(each.value.virtual_network_subnet_id, null)

  diagnostic_settings = try({
    for s in each.value.diagnostic_settings : s.name => {
      name                  = try(s.name, "diag-${each.value.name}")
      workspace_resource_id = try(data.azurerm_log_analytics_workspace.this[each.key].id, null)
      log_groups            = ["audit", "allLogs"]
    }
  }, {})

  managed_identities = {
    system_assigned            = try(each.value.managed_identities.system_assigned, true)
    user_assigned_resource_ids = try(each.value.managed_identities.user_assigned_resource_ids, [])
  }

  app_settings = try(each.value.app_settings, {})

  site_config = try({
    always_on       = try(each.value.site_config.always_on, false)
    app_scale_limit = try(each.value.site_config.app_scale_limit, 1)
    cors = try(each.value.site_config.cors != null ? {
      allowed_origins     = try(each.value.site_config.cors.allowed_origins, ["https://portal.azure.com", ])
      support_credentials = try(each.value.site_config.cors.support_credentials, true)
    } : null, null)
    ftps_state                       = try(each.value.site_config.ftps_state, "Disabled")
    http2_enabled                    = try(each.value.site_config.http2_enabled, false)
    scm_use_main_ip_restriction      = try(each.value.site_config.scm_use_main_ip_restriction, null)
    scm_min_tls_version              = try(each.value.site_config.scm_min_tls_version, null)
    scm_type                         = try(each.value.site_config.scm_type, null)
    linux_fx_version                 = try(each.value.site_config.linux_fx_version, null)
    min_tls_version                  = try(each.value.site_config.min_tls_version, null)
    pre_warmed_instance_count        = try(each.value.site_config.pre_warmed_instance_count, null)
    public_network_access_enabled    = try(each.value.site_config.public_network_access_enabled, false)
    runtime_scale_monitoring_enabled = try(each.value.site_config.runtime_scale_monitoring_enabled, null)
    vnet_route_all_enabled           = try(each.value.site_config.vnet_route_all_enabled, true)
    websockets_enabled               = try(each.value.site_config.websockets_enabled, true)
  }, {})

  private_endpoints = try({
    for s in each.value.private_endpoints : s.subresource_name => {
      subresource_name              = s.subresource_name
      private_dns_zone_resource_ids = try([local.dns_zones[local.subresource_to_dns_zone[s.subresource_name]]], [])
      subnet_resource_id            = data.azurerm_subnet.pvt[each.key].id
    }
  }, {})

  role_assignments = {
    for s in each.value.role_assignments : s.resourcename => {
      principal_id               = try(contains(keys(azuread_group.this), s.principal_id) ? replace(replace(azuread_group.this[s.principal_id].id, "/groups/", ""), "/", "") : s.principal_id, null)
      role_definition_id_or_name = try(s.role_definition_id_or_name, null)
    }
  }
}
