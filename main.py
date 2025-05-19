#!/usr/bin/env python3

"""
Interactive Terminal Chat for Aduro AI Health Assistant

This script provides an interactive terminal interface to chat with the
Aduro AI Health Assistant, which coordinates between different specialized agents
to handle user profile management, CGM readings, and meal planning.
"""

import asyncio
import atexit
import os
import readline
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Import agents after setting up sys.path
sys.path.insert(0, os.path.abspath('./agents'))
from orchestrator import Orchestrator

# Set up command history file
HISTORY_FILE = os.path.expanduser('~/.aduro_ai_history')

def init_readline():
    """Initialize readline with tab completion and history."""
    # Enable tab completion
    readline.parse_and_bind('tab: complete')
    
    # Set up history file
    try:
        readline.read_history_file(HISTORY_FILE)
        # Set history length to 1000 lines
        readline.set_history_length(1000)
    except FileNotFoundError:
        open(HISTORY_FILE, 'a').close()
    
    # Save history on exit
    atexit.register(readline.write_history_file, HISTORY_FILE)

# Initialize readline
init_readline()

# Database path
DB_PATH = Path("db/users.db")

# ANSI color codes for terminal output
COLORS = {
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
    "RED": "\033[91m",
    "GREEN": "\033[92m",
    "YELLOW": "\033[93m",
    "BLUE": "\033[94m",
    "MAGENTA": "\033[95m",
    "CYAN": "\033[96m",
}


async def ensure_database():
    """Ensure the database exists and has necessary tables."""
    # Create db directory if it doesn't exist
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    # Connect to the database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Create users table if it doesn't exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT,
        last_name TEXT,
        city TEXT,
        email TEXT UNIQUE,
        date_of_birth DATE,
        dietary_preference TEXT CHECK(dietary_preference IN ('vegetarian', 'non-vegetarian', 'vegan')),
        medical_conditions TEXT,
        physical_limitations TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Create CGM readings table if it doesn't exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cgm_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        reading REAL,
        reading_type TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """)
    
    # Commit changes and close connection
    conn.commit()
    conn.close()


async def ensure_test_user():
    """Ensure a test user exists in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if test user exists
    cursor.execute("SELECT id FROM users WHERE id = 1")
    if not cursor.fetchone():
        # Create a test user
        cursor.execute("""
        INSERT INTO users (id, first_name, email)
        VALUES (1, 'Test', 'test@example.com')
        """)
        print(f"{COLORS['GREEN']}Created test user with ID 1{COLORS['RESET']}")
    
    # Commit changes and close connection
    conn.commit()
    conn.close()
    return 1  # Return the test user ID


async def list_users():
    """List all users in the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all users
    cursor.execute("SELECT id, first_name, last_name, email FROM users")
    users = cursor.fetchall()
    
    # Close connection
    conn.close()
    
    if not users:
        print(f"{COLORS['YELLOW']}No users found.{COLORS['RESET']}")
        return
    
    # Print users
    print(f"\n{COLORS['BOLD']}Available Users:{COLORS['RESET']}")
    print("-" * 50)
    for user in users:
        print(f"ID: {user['id']}, Name: {user['first_name']} {user['last_name'] or ''}, Email: {user['email'] or ''}")
    print("-" * 50)


async def create_new_user():
    """Create a new user in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get user information
    print(f"\n{COLORS['BOLD']}Create a New User:{COLORS['RESET']}")
    first_name = input("First Name: ")
    email = input("Email: ")
    
    # Insert user
    cursor.execute("""
    INSERT INTO users (first_name, email, created_at)
    VALUES (?, ?, ?)
    """, (first_name, email, datetime.datetime.now()))
    
    # Get the new user's ID
    user_id = cursor.lastrowid
    
    # Commit changes and close connection
    conn.commit()
    conn.close()
    
    print(f"{COLORS['GREEN']}Created new user with ID {user_id}{COLORS['RESET']}")
    return user_id


async def check_user_profile(user_id):
    """Check if user has a complete profile."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get user profile
    cursor.execute("""
    SELECT first_name, last_name, city, email, date_of_birth, dietary_preference
    FROM users
    WHERE id = ?
    """, (user_id,))
    
    profile = cursor.fetchone()
    conn.close()
    
    if not profile:
        return False, {}
    
    # Convert to dict
    profile_dict = dict(profile)
    
    # Check required fields
    required_fields = ["first_name", "last_name", "city", "email", "date_of_birth", "dietary_preference"]
    complete = all(profile_dict.get(field) for field in required_fields)
    
    return complete, profile_dict


async def check_user_cgm(user_id):
    """Check if user has CGM readings."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get CGM readings count
    cursor.execute("""
    SELECT COUNT(*) FROM cgm_readings WHERE user_id = ?
    """, (user_id,))
    
    count = cursor.fetchone()[0]
    conn.close()
    
    return count > 0


async def print_user_status(user_id):
    """Print user status information."""
    complete, profile = await check_user_profile(user_id)
    has_cgm = await check_user_cgm(user_id)
    
    print(f"\n{COLORS['BOLD']}User Status:{COLORS['RESET']}")
    print("-" * 50)
    print(f"User ID: {user_id}")
    print(f"Profile Complete: {'✅' if complete else '❌'}")
    print(f"CGM Readings: {'✅' if has_cgm else '❌'}")
    
    if profile:
        print(f"\n{COLORS['BOLD']}Profile Information:{COLORS['RESET']}")
        for key, value in profile.items():
            if value:  # Only show non-empty fields
                print(f"{key.replace('_', ' ').title()}: {value}")
    
    print("-" * 50)


async def chat_session(orchestrator, user_id):
    """Start an interactive chat session with the agent."""
    # Initialize the context with user_id
    context = {"user_id": user_id}
    
    # Check if profile is complete
    profile_complete, _ = await check_user_profile(user_id)
    context["profile_complete"] = profile_complete
    
    # Check if CGM readings are available
    cgm_collected = await check_user_cgm(user_id)
    context["cgm_collected"] = cgm_collected
    
    print(f"\n{COLORS['CYAN']}Starting chat with Aduro AI Health Assistant...{COLORS['RESET']}")
    print(f"{COLORS['CYAN']}Type 'exit', 'quit', or 'bye' to end the session.{COLORS['RESET']}")
    print(f"{COLORS['CYAN']}Type 'status' to see your current profile status.{COLORS['RESET']}")
    print("-" * 50)
    
    # Send a greeting to the orchestrator
    response = await orchestrator.handle_message("Hello", context)
    print(f"\n{COLORS['GREEN']}AI: {response}{COLORS['RESET']}")
    
    # Start the conversation loop
    while True:
        # Get user input
        try:
            user_input = input(f"\n{COLORS['BLUE']}You: {COLORS['RESET']}")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting chat session...")
            break
        
        # Check for exit commands
        if user_input.lower() in ["exit", "quit", "bye"]:
            print("Exiting chat session...")
            break
        
        # Check for status command
        if user_input.lower() == "status":
            await print_user_status(user_id)
            continue
        
        # Get response from the orchestrator
        try:
            response = await orchestrator.handle_message(user_input, context)
            print(f"\n{COLORS['GREEN']}AI: {response}{COLORS['RESET']}")
        except Exception as e:
            print(f"\n{COLORS['RED']}Error: {str(e)}{COLORS['RESET']}")


async def main_menu():
    """Display the main menu and handle user selections."""
    # Create an instance of the orchestrator
    orchestrator = Orchestrator()
    
    while True:
        print(f"\n{COLORS['BOLD']}Aduro AI Health Assistant{COLORS['RESET']}")
        print("-" * 50)
        print("1. Chat with existing user")
        print("2. Create new user")
        print("3. List all users")
        print("4. Quit")
        print("-" * 50)
        
        # Get user selection
        choice = input("Select an option (1-4): ")
        
        if choice == "1":
            # List users first
            await list_users()
            
            # Get user ID
            try:
                user_id = int(input("Enter user ID: "))
                await print_user_status(user_id)
                await chat_session(orchestrator, user_id)
            except ValueError:
                print(f"{COLORS['RED']}Invalid user ID. Please enter a number.{COLORS['RESET']}")
        
        elif choice == "2":
            user_id = await create_new_user()
            await chat_session(orchestrator, user_id)
        
        elif choice == "3":
            await list_users()
        
        elif choice == "4":
            print("Goodbye!")
            break
        
        else:
            print(f"{COLORS['RED']}Invalid selection. Please try again.{COLORS['RESET']}")


async def main():
    """Main entry point for the application."""
    try:
        # Load environment variables
        load_dotenv()
        
        # Ensure database exists
        await ensure_database()
        
        # Ensure test user exists
        await ensure_test_user()
        
        # Start the main menu
        await main_menu()
        
    except Exception as e:
        print(f"\n{COLORS['RED']}An error occurred: {str(e)}{COLORS['RESET']}")
        print("Please make sure you have set up your environment correctly.")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
