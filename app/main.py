import streamlit as st
import os
from rag_engine import TerraformRAGEngine

# Set page config
st.set_page_config(
    page_title="Terraform AI Agent",
    page_icon="🤖",
    layout="wide"
)

# Add debug mode toggle
debug_mode = st.sidebar.checkbox("Debug Mode", value=True)

# Initialize the RAG engine with debug mode
st.write("🔍 Initializing TerraformRAGEngine...")
try:
    # Get the absolute path to the templates directory
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(current_dir, 'templates')
    
    if debug_mode:
        st.write(f"📁 Template directory: {template_dir}")
        st.write("📄 Checking template files...")
        template_files = os.listdir(template_dir)
        st.write(f"Found {len(template_files)} template files:")
        for file in template_files:
            st.write(f"- {file}")
    
    # Initialize the RAG engine
    rag_engine = TerraformRAGEngine(template_dir=template_dir, debug_mode=debug_mode)
    
    if debug_mode:
        st.success("✅ TerraformRAGEngine initialized successfully")
except Exception as e:
    st.error(f"❌ Error initializing TerraformRAGEngine: {str(e)}")
    st.stop()

# Main interface
st.title("🤖 Terraform AI Agent")
st.write("Generate Terraform configurations using natural language")

# Query input
query = st.text_area(
    "Enter your infrastructure requirements:",
    placeholder="e.g., Create a resource group called test-rg in eastus",
    height=100
)

# Generate button
if st.button("Generate Terraform"):
    if not query:
        st.warning("Please enter your infrastructure requirements")
    else:
        try:
            with st.spinner("Generating Terraform configuration..."):
                if debug_mode:
                    st.write("🔍 Processing query...")
                    st.write(f"📝 Query: {query}")
                
                # Generate the Terraform configuration
                result = rag_engine.generate_terraform(query)
                
                if debug_mode:
                    st.success("✅ Terraform configuration generated successfully")
                
                # Display the result
                st.subheader("Generated Terraform Configuration")
                st.code(result, language="hcl")
                
        except Exception as e:
            st.error(f"Error generating Terraform configuration: {str(e)}")
            if debug_mode:
                st.exception(e)

# Footer
st.markdown("---")
st.markdown("© 2025 Terraform AI Agent | Powered by Azure OpenAI") 