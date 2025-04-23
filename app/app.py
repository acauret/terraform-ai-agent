import os
import streamlit as st
from master_agent import MasterAgent
import json
import time
import base64
from dotenv import load_dotenv
from check_templates import check_templates

# Load environment variables
load_dotenv()

# Check templates directory first
check_templates()

# Set page configuration
st.set_page_config(
    page_title="Azure Terraform Generator",
    page_icon="🌩️",
    layout="wide"
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "generated_configs" not in st.session_state:
    st.session_state.generated_configs = []

if "debug_mode" not in st.session_state:
    st.session_state.debug_mode = False

if "current_terraform_code" not in st.session_state:
    st.session_state.current_terraform_code = ""

if "current_tfvars_content" not in st.session_state:
    st.session_state.current_tfvars_content = ""

if "current_entra_tfvars_content" not in st.session_state:
    st.session_state.current_entra_tfvars_content = ""

if "current_tfvars_filename" not in st.session_state:
    st.session_state.current_tfvars_filename = "terraform.tfvars"

if "current_main_tf_content" not in st.session_state:
    st.session_state.current_main_tf_content = ""

# App header
st.title("Azure Terraform Generator")
st.subheader("Generate Terraform configurations with natural language")

# Sidebar
with st.sidebar:
    st.header("Settings")
    
    # Debug mode toggle
    debug_mode = st.checkbox("🛠️ Debug Mode", value=st.session_state.debug_mode, 
                          help="Toggle debug information display")
    if debug_mode != st.session_state.debug_mode:
        st.session_state.debug_mode = debug_mode
        st.rerun()
    
    # About section
    st.header("About")
    st.markdown("""
    This application uses AI to generate Terraform configurations for Azure resources.
    Simply describe what you want to build, and the agent will create the Terraform code.
    """)

# Initialize the master agent (with error handling)
try:
    # Get templates directory path
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    master_agent = MasterAgent(templates_dir)
except Exception as e:
    st.error(f"Failed to initialize the master agent: {str(e)}")
    st.stop()

# Always display download buttons for the latest configuration if available
if st.session_state.generated_configs:
    st.sidebar.markdown("### Download Files")
    
    if st.session_state.current_main_tf_content:
        st.sidebar.download_button(
            label="📥 Download Main Config",
            data=st.session_state.current_main_tf_content,
            file_name="main.tf",
            mime="text/plain",
            key="sidebar_main"
        )
    
    for config in st.session_state.generated_configs:
        st.sidebar.download_button(
            label=f"📥 Download {config['filename']}",
            data=config['content'],
            file_name=config['filename'],
            mime="text/plain",
            key=f"sidebar_{config['type']}"
        )

# Add base main.tf download option
with st.sidebar.expander("📄 Base Terraform Configuration"):
    st.markdown("Download the base Terraform configuration with provider setup and variable declarations.")
    try:
        main_tf_content = master_agent.get_main_tf_content()
        st.download_button(
            label="📥 Download Base Configuration",
            data=main_tf_content,
            file_name="main.tf",
            mime="text/plain",
            key="download_base_expander"
        )
    except Exception as e:
        st.error(f"Error loading main.tf: {str(e)}")

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat control buttons
chat_control_container = st.container()
with chat_control_container:
    col1, col2 = st.columns([9, 1])
    with col2:
        if st.button("🗑️ Clear Chat", key="clear_chat", help="Clear chat history"):
            # Clear chat history and generated code
            st.session_state.messages = []
            st.session_state.generated_configs = []
            st.session_state.current_terraform_code = ""
            st.session_state.current_tfvars_content = ""
            st.session_state.current_entra_tfvars_content = ""
            st.session_state.current_tfvars_filename = "terraform.tfvars"
            st.session_state.current_main_tf_content = ""
            st.rerun()

# Handle user input
if prompt := st.chat_input("Describe the Azure resources you want to create..."):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Display assistant response with a spinner while generating
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        with st.spinner("Generating Terraform configuration..."):
            try:
                # Process the request through the master agent
                start_time = time.time()
                result = master_agent.process_request(prompt)
                processing_time = time.time() - start_time
                
                if not result["success"]:
                    message_placeholder.error(result["message"])
                    st.session_state.messages.append({"role": "assistant", "content": f"❌ {result['message']}"})
                else:
                    # Store the generated configurations
                    st.session_state.generated_configs = result["configs"]
                    st.session_state.current_main_tf_content = result.get("main_tf", "")
                    
                    # Display success message
                    confirmation = f"✅ Generated {len(result['configs'])} configuration file(s) in {processing_time:.2f} seconds."
                    message_placeholder.success(confirmation)
                    
                    # Display the combined output in a code block
                    if "combined" in result:
                        st.code(result["combined"], language="hcl")
                    
                    # Store assistant message
                    content = f"{confirmation}\n\n```hcl\n{result['combined']}\n```"
                    st.session_state.messages.append({"role": "assistant", "content": content})
                    
                    # Debug information
                    if st.session_state.debug_mode:
                        st.subheader("Debug Information")
                        st.json(result)
            
            except Exception as e:
                error_message = f"Error processing request: {str(e)}"
                message_placeholder.error(error_message)
                st.session_state.messages.append({"role": "assistant", "content": f"❌ {error_message}"})

# Display download options for generated configs
if st.session_state.generated_configs:
    st.subheader("Generated Terraform Files")
    
    # First, display the main.tf if available
    if st.session_state.current_main_tf_content:
        st.markdown("### Base Terraform Configuration")
        st.code(st.session_state.current_main_tf_content[:2000] + "..." if len(st.session_state.current_main_tf_content) > 2000 else st.session_state.current_main_tf_content, language="hcl")
        st.download_button(
            label="Download main.tf",
            data=st.session_state.current_main_tf_content,
            file_name="main.tf",
            mime="text/plain",
            key="download_main_tf"
        )
        st.markdown("---")
    
    # Create columns for each configuration file
    cols = st.columns(min(3, len(st.session_state.generated_configs)))
    
    # Display each configuration in a separate column with download button
    for i, config in enumerate(st.session_state.generated_configs):
        col_index = i % 3
        with cols[col_index]:
            st.markdown(f"### {config['type'].replace('_', ' ').title()}")
            st.code(config['content'], language="hcl")
            
            # Create download button for the configuration
            st.download_button(
                label=f"Download {config['filename']}",
                data=config['content'],
                file_name=config['filename'],
                mime="text/plain",
                key=f"download_{config['type']}"
            ) 