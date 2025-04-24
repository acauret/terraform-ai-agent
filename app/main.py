import streamlit as st

# Set page configuration - must be the very first Streamlit command
st.set_page_config(
    page_title="Terraform AI Agent",
    page_icon="🤖",
    layout="wide"
)

# Now import the rest of the modules
import os
import json
import dotenv
from agents.agent_factory import AgentFactory

# Load environment variables from the specific absolute path
dotenv_path = r"E:\Git\GitHub\terraform-ai-agent\.env"
dotenv.load_dotenv(dotenv_path)
st.write(f"Loading .env from: {dotenv_path}")
st.write(f"File exists: {os.path.exists(dotenv_path)}")
st.write(f"AZURE_OPENAI_API_KEY exists: {os.getenv('AZURE_OPENAI_API_KEY') is not None}")

# Constants
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

# Create the agent factory
agent_factory = AgentFactory(TEMPLATES_DIR)

# Debug environment variables for each agent
st.subheader("Agent Initialization Debug Info")
for agent_type in agent_factory.agents:
    st.write(f"Debug for {agent_type} agent:")
    agent_factory.agents[agent_type].debug_env_variables()
    st.write("---")

# Title and description
st.title("Terraform AI Agent")
st.markdown("""
This application generates Terraform configuration files for Azure resources based on natural language input.
Simply describe what you want to create, and the AI will generate the appropriate Terraform configuration.
""")

# User input
query = st.text_area("What would you like to create in Azure? (e.g., 'Create a resource group rg-test with role assignments for tester and operator')", height=100)

# Generate button
if st.button("Generate Terraform Configuration"):
    if query:
        # Show spinner while processing
        with st.spinner("Generating Terraform configuration..."):
            try:
                # Process the query using the agent factory
                result = agent_factory.process_query(query)
                
                if result["success"]:
                    st.success(result["message"])
                    
                    # Create tabs for individual files and combined output
                    if result["configs"]:
                        tabs = []
                        tabs.append("Combined Output")
                        for config in result["configs"]:
                            tabs.append(config["filename"])
                        tabs.append("main.tf")
                        
                        selected_tab = st.tabs(tabs)
                        
                        # Combined output tab
                        with selected_tab[0]:
                            st.code(result["combined"], language="hcl")
                            
                        # Individual file tabs
                        for i, config in enumerate(result["configs"], start=1):
                            with selected_tab[i]:
                                st.code(config["content"], language="hcl")
                                
                        # main.tf tab
                        with selected_tab[-1]:
                            st.code(result["main_tf"], language="hcl")
                            
                        # Download buttons
                        st.subheader("Download Files")
                        cols = st.columns(len(result["configs"]) + 1)
                        
                        for i, config in enumerate(result["configs"]):
                            cols[i].download_button(
                                label=f"Download {config['filename']}",
                                data=config["content"],
                                file_name=config["filename"],
                                mime="text/plain"
                            )
                            
                        if result["main_tf"]:
                            cols[-1].download_button(
                                label="Download main.tf",
                                data=result["main_tf"],
                                file_name="main.tf",
                                mime="text/plain"
                            )
                else:
                    st.error(result["message"])
                    
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
    else:
        st.warning("Please enter a query first.")

# Footer
st.markdown("---")
st.markdown("© 2025 Terraform AI Agent | Powered by Azure OpenAI") 