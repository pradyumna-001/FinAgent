import os
import sys
import logging
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.company import company_agent_node

# Configure verbose logging to watch the agent execution
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Load real environment variables from your local .env file
load_dotenv()

def run_live_test():
    print("\n--- STARTING LIVE COMPANY AGENT RUN ---")
    
    initial_state = {
        "pipeline_run_id": "live-company-run",
        "morning_note_id": "live-company-note",
        "company_ticker": "PETR4",
        "company_events": [],
        "flags": [],
        "data_freshness": {}
    }
    
    final_state = company_agent_node(initial_state)
    
    print("\n--- LIVE RUN RESULTS ---")
    print(f"Target Ticker Analyzed: {final_state.get('company_ticker')}")
    print(f"Data Flags Recorded: {final_state['flags']}")
    print(f"Data Freshness Map: {final_state.get('data_freshness')}")
    print(f"Extracted Company Events Count: {len(final_state.get('company_events', []))}")
    
    print("\nExtracted Events Detail:")
    for idx, event in enumerate(final_state.get("company_events", []), 1):
        print(f"\n[{idx}] {event.event_name} ({event.event_date}) - Impact: {event.significance}")
        print(f"    Description: {event.description}")
        
    print("--------------------------------------\n")

if __name__ == "__main__":
    if not os.getenv("OPENROUTER_API_KEY") or not os.getenv("TAVILY_API_KEY"):
        print("ERROR: Please ensure OPENROUTER_API_KEY and TAVILY_API_KEY are configured in your .env file.")
    else:
        run_live_test()