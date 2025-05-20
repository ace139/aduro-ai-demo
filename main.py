#!/usr/bin/env python3

"""
Aduro AI Health Assistant - Main Entry Point

This script provides a command-line interface for the Aduro AI Health Assistant,
which uses a TriageAgent to route requests to specialized agents for different
health-related tasks.
"""

import argparse
import asyncio
import os
import readline
from datetime import datetime
from typing import Any

from agents import RunContextWrapper, Runner

from aduro_agents.models import AduroConversationContext, ProfileStatus
from aduro_agents.triage_agent import TriageAgent

# Set up command history file
HISTORY_FILE = os.path.expanduser('~/.aduro_ai_history')


def init_readline() -> None:
    """Initialize readline with tab completion and history."""
    # Enable tab completion
    readline.parse_and_bind('tab: complete')

    # Set up history file
    try:
        readline.read_history_file(HISTORY_FILE)
        readline.set_history_length(1000)
    except FileNotFoundError:
        open(HISTORY_FILE, 'a').close()

    # Save history on exit
    import atexit
    atexit.register(readline.write_history_file, HISTORY_FILE)


def print_welcome() -> None:
    """Print the welcome message and usage instructions."""
    print("\n" + "=" * 70)
    print("Aduro AI Health Assistant".center(70))
    print("=" * 70)
    print("\nI can help you with:")
    print("  • Setting up your health profile")
    print("  • Recording and analyzing CGM readings")
    print("  • Creating personalized meal plans")
    print("  • Updating your profile information")
    print("\nType 'exit' or 'quit' to end the session")
    print("-" * 70 + "\n")


def create_initial_context(user_id: int | None = None, debug: bool = False) -> dict[str, Any]:
    """
    Create the initial context dictionary for the conversation.

    Args:
        user_id: Optional user ID to use for the session
        debug: Whether to enable debug output

    Returns:
        A dictionary containing the initial context
    """
    from uuid import uuid4

    # Create a new conversation context
    conversation_context = AduroConversationContext(
        user_id=user_id or 1,  # Default to user 1 if not specified
        profile_status=ProfileStatus.NOT_STARTED,
        has_cgm_data=False,
        last_interaction=datetime.utcnow()
    )

    return {
        # User identification
        'user_id': user_id or 1,  # Default to user 1 if not specified
        'session_id': str(uuid4()),

        # System settings
        'debug': debug,
        'start_time': datetime.now().isoformat(),

        # Conversation state
        'message_count': 0,
        'last_message': None,
        'conversation_history': [],

        # Conversation context
        'conversation_context': conversation_context,

        # User context (will be populated during the conversation)
        'user_context': {
            'profile_complete': False,
            'cgm_connected': False,
            'preferences': {}
        }
    }


async def run_conversation(user_id: int | None = None, debug: bool = False) -> None:
    """
    Run the main conversation loop with the TriageAgent.

    This function initializes the TriageAgent and enters a loop that:
    1. Takes natural language input from the user
    2. Processes it through the TriageAgent
    3. Displays the response
    4. Maintains conversation context

    Args:
        user_id: Optional user ID to use for the session
        debug: Whether to enable debug output
    """
    print("Initializing Aduro AI Health Assistant...")

    try:
        # Set up the database path
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db', 'users.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # Initialize the agent
        triage_agent = TriageAgent(db_path=db_path)

        # Set up the initial context
        context = create_initial_context(user_id, debug)

        # Print welcome message
        print_welcome()

        # Main conversation loop
        while True:
            try:
                # Get user input
                try:
                    user_input = input("\nYou: ").strip()

                    # Update context with user message
                    context['last_message'] = user_input
                    context['message_count'] += 1
                    context['conversation_history'].append({
                        'role': 'user',
                        'content': user_input,
                        'timestamp': datetime.now().isoformat()
                    })

                except (EOFError, KeyboardInterrupt):
                    print("\n\nGoodbye!")
                    break

                # Check for exit conditions
                if not user_input:
                    continue

                if user_input.lower() in ('exit', 'quit', 'bye', 'goodbye'):
                    print("\nGoodbye! Thanks for using Aduro AI Health Assistant.")
                    break

                # Process the input through the agent
                try:
                    # Create a context wrapper with our context (not used directly but needed for the agent)
                    _ = RunContextWrapper(context=context)

                    # Run the agent
                    response = await Runner.run(
                        triage_agent,
                        user_input,
                        context=context
                    )

                    # Extract the final output
                    assistant_response = response.final_output

                    # Update the conversation context with the latest interaction
                    if 'conversation_context' in context:
                        context['conversation_context'].last_interaction = datetime.utcnow()

                    # Update context with assistant response
                    context['conversation_history'].append({
                        'role': 'assistant',
                        'content': assistant_response,
                        'timestamp': datetime.now().isoformat(),
                        'context': context.get('conversation_context').model_dump() if 'conversation_context' in context else {}
                    })

                    # Print the response with some formatting
                    print("\n" + "=" * 70)

                    # Add context information to the response if in debug mode
                    if context.get('debug', False) and 'conversation_context' in context:
                        ctx = context['conversation_context']
                        print(f"[DEBUG] Profile Status: {ctx.profile_status.value}")
                        print(f"[DEBUG] Has CGM Data: {ctx.has_cgm_data}")
                        print(f"[DEBUG] Last Interaction: {ctx.last_interaction}")
                        print("-" * 70)

                    print(f"Assistant: {assistant_response}")
                    print("=" * 70)

                except Exception as e:
                    error_msg = f"I'm sorry, I encountered an error: {e!s}"
                    print(f"\n{error_msg}")

                    if debug:
                        import traceback
                        print("\nDebug information:")
                        traceback.print_exc()

                    # Log the error in context
                    context['conversation_history'].append({
                        'role': 'system',
                        'content': f'Error: {e!s}',
                        'timestamp': datetime.now().isoformat()
                    })

                    # Print the error message to the user
                    print(f"\nError: {e!s}")

            except Exception as e:
                error_msg = "An unexpected error occurred. Please try again."
                print(f"\n{error_msg}")
                if debug:
                    import traceback
                    print(f"Debug: {e!s}")
                    traceback.print_exc()

                # Log the error in context if context is available
                if 'conversation_history' in context:
                    context['conversation_history'].append({
                        'role': 'system',
                        'content': f'Unexpected error: {e!s}',
                        'timestamp': datetime.now().isoformat()
                    })

    except Exception as e:
        print(f"\nFailed to initialize the application: {e!s}")
        if debug:
            import traceback
            traceback.print_exc()


async def test_handoff(debug: bool = False) -> None:
    """Test the handoff functionality from TriageAgent to GreeterProfiler."""
    print("\n=== Testing Handoff to GreeterProfiler ===\n")

    # Set up the database path
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db', 'users.db')
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Initialize the agent
    triage_agent = TriageAgent(db_path=db_path)

    # Test message that should trigger GreeterProfiler
    test_message = "I want to create a new profile"
    context = {'user_id': 999, 'debug': debug}  # Using a test user ID

    print(f"Sending test message: \"{test_message}\"")
    print("Expected behavior: This should be handled by the GreeterProfiler agent\n")

    try:
        # Process the test message using the return_dict parameter to get agent info
        response = await triage_agent.process_input(test_message, context=context, return_dict=True)

        # Print the response message
        print(f"\nResponse from agent: {response['message']}")

        # Verify the handoff occurred by checking the agent_name in the response
        if 'agent_name' in response and 'greeter' in response['agent_name'].lower():
            print(f"\n✅ Success: Message was correctly handed off to {response['agent_name']}")
        else:
            print("\n❌ Warning: Message may not have been handed off to GreeterProfiler")
            if debug:
                print(f"Agent that handled the request: {response.get('agent_name', 'Unknown')}")

    except Exception as e:
        print(f"\n❌ Error during handoff test: {e!s}")
        if debug:
            import traceback
            traceback.print_exc()

    print("\n=== End of Handoff Test ===\n")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Aduro AI Health Assistant')
    parser.add_argument('--user-id', type=int, help='User ID to use for the session')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--test-handoff', action='store_true',
                       help='Run a test of the agent handoff functionality')
    return parser.parse_args()


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_arguments()

    # Initialize readline for better input handling
    init_readline()

    try:
        if args.test_handoff:
            # Run the handoff test
            asyncio.run(test_handoff(debug=args.debug))
        else:
            # Run the main conversation loop
            asyncio.run(run_conversation(user_id=args.user_id, debug=args.debug))
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as e:
        print(f"\nAn error occurred: {e!s}")
        if args.debug:
            import traceback
            traceback.print_exc()
        raise
