# Terraform AI Agent

An AI-powered assistant that generates Terraform configurations for Azure resources based on natural language descriptions.

## Features

- **Natural Language Interface**: Describe the Azure resources you want to create in plain English
- **Multi-Resource Support**: Generate configurations for multiple resource types in a single request
- **Role Assignment Handling**: Automatically generates Entra Groups for role assignments
- **Interactive UI**: Chat-based interface with response history
- **Downloadable Files**: Generated Terraform files can be downloaded directly
- **Debug Mode**: Enable debug mode to see detailed information about the generation process

## Supported Azure Resources

- Resource Groups
- Storage Accounts
- Key Vaults
- Entra ID Groups (automatically generated for role assignments)

## Example Queries

Here are some example queries you can try:

- "Create a resource group called 'my-project' in East US with role assignments for admin and operator"
- "I need a storage account with private endpoints and containers"
- "Set up a key vault in West US"
- "Create a resource group, a storage account, and a key vault with role assignments for developers"

## Installation

### Prerequisites

- Python 3.8+
- Azure OpenAI API key

### Environment Setup

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/terraform-ai-agent.git
   cd terraform-ai-agent
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   ```
   export AZURE_OPENAI_API_KEY=your_api_key
   export AZURE_OPENAI_ENDPOINT=your_endpoint
   export AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=your_deployment_name
   export AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME=your_embedding_deployment_name
   ```

## Running the Application

Start the Streamlit app:
```
streamlit run app/app.py
```

Then open your browser at `http://localhost:8501` to use the application.

## How It Works

1. The master agent analyzes your query to determine what Azure resources you need
2. Specialized agents handle the generation of specific resource types
3. If role assignments are detected, an Entra groups agent creates the necessary configurations
4. All generated configurations are combined and presented to you
5. You can download individual configuration files for use in your Terraform project

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 