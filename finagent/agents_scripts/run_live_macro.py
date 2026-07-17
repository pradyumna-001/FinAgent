# run_live_macro.py
import os
import logging
from dotenv import load_dotenv
from app.agents.macro import macro_agent_node

# Configure verbose logging to watch the agent execution
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Load real environment variables from your local .env file
load_dotenv()

def run_live_test():
    print("\n--- STARTING LIVE MACRO AGENT RUN ---")
    
    # Initialize a mock pipeline state
    initial_state = {
        "pipeline_run_id": "live-test-run",
        "morning_note_id": "live-test-note",
        "macro_context": None,
        "flags": [],
        "data_freshness": {}
    }
    
    # Execute the agent node
    final_state = macro_agent_node(initial_state)
    
    print("\n--- LIVE RUN RESULTS ---")
    print(f"Data Flags Recorded: {final_state['flags']}")
    print(f"Data Freshness Map: {final_state.get('data_freshness')}")
    print(f"Macro Context Output: {final_state['macro_context']}")
    print("--------------------------------------\n")

if __name__ == "__main__":
    # Quick sanity check for credentials
    if not os.getenv("OPENROUTER_API_KEY") or not os.getenv("TAVILY_API_KEY"):
        print("ERROR: Please ensure OPENROUTER_API_KEY and TAVILY_API_KEY are configured in your .env file.")
    else:
        run_live_test()
