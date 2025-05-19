from dotenv import load_dotenv
from agents import Agent, Runner

def main():
    try:
        # Load environment variables from .env file
        load_dotenv()
        
        # Create an agent
        agent = Agent(
            name="Assistant",
            instructions="You are a helpful assistant that writes creative content."
        )
        
        # Run the agent with a prompt
        result = Runner.run_sync(
            agent, 
            "Write a haiku about recursion in programming."
        )
        
        # Print the result
        print("\nAgent's Response:")
        print("-" * 50)
        print(result.final_output)
        print("-" * 50)
        
    except Exception as e:
        print(f"An error occurred: {e}")
        print("Please make sure you have set up your .env file with the required API keys.")
        print("You need to set the OPENAI_API_KEY environment variable.")

if __name__ == "__main__":
    main()
