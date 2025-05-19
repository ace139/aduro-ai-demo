#!/usr/bin/env python3

"""
Interactive Terminal Chat for Aduro AI Health Assistant (Demo Mode)

This script provides a demonstration of the Aduro AI Health Assistant
with mocked agent behaviors for demonstration and testing purposes.
"""

import asyncio
import datetime
import os
import sqlite3
from pathlib import Path

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

# Database path
DB_PATH = Path("db/users.db")


class MockOrchestrator:
    """Mock version of the Orchestrator that demonstrates the flow."""
    
    async def handle_message(self, message: str, context: dict) -> str:
        """
        Process an incoming message and demonstrate the flow.
        
        Args:
            message: The raw user text
            context: Dictionary carrying state and user information
                
        Returns:
            Response message demonstrating the appropriate agent
        """
        # 1. Authenticate - validate user_id exists
        if 'user_id' not in context or not isinstance(context.get('user_id'), int):
            return "⚠️ Missing or invalid user ID. Please re-authenticate."
        
        # 2. Profile Phase
        if not context.get("profile_complete", False):
            # If awaiting a specific profile field
            if context.get("awaiting_profile_field", False) and "field_to_update" in context:
                field = context["field_to_update"]
                
                # Mock profile updater behavior
                if "dietary" in field:
                    if any(x in message.lower() for x in ["vegan", "vegetarian", "non-vegetarian"]):
                        # Update field in DB
                        await self._update_field(context["user_id"], field, message.lower())
                        
                        # Find next missing field or mark complete
                        missing = await self._get_missing_fields(context["user_id"])
                        if not missing:
                            context["profile_complete"] = True
                            context["awaiting_profile_field"] = False
                            return "🎉 Your profile is now complete! Let's collect your CGM readings next. Please enter your blood sugar readings separated by commas."
                        else:
                            context["field_to_update"] = missing[0]
                            return f"Thanks! I've updated your dietary preference. What's your {missing[0].replace('_', ' ')}?"
                    else:
                        return "Please enter a valid dietary preference: vegetarian, non-vegetarian, or vegan."
                
                if "last_name" in field:
                    # Update field in DB
                    await self._update_field(context["user_id"], field, message)
                    
                    # Find next missing field
                    missing = await self._get_missing_fields(context["user_id"])
                    context["field_to_update"] = missing[0]
                    return f"Thanks! I've updated your last name. What's your {missing[0].replace('_', ' ')}?"
                
                if "city" in field:
                    # Update field in DB
                    await self._update_field(context["user_id"], field, message)
                    
                    # Find next missing field
                    missing = await self._get_missing_fields(context["user_id"])
                    context["field_to_update"] = missing[0]
                    return f"Thanks! I've updated your city. What's your {missing[0].replace('_', ' ')}?"
                
                if "date_of_birth" in field:
                    # Validate format
                    if "-" in message and len(message.split("-")) == 3:
                        # Update field in DB
                        await self._update_field(context["user_id"], field, message)
                        
                        # Find next missing field
                        missing = await self._get_missing_fields(context["user_id"])
                        context["field_to_update"] = missing[0]
                        return f"Thanks! I've updated your date of birth. What's your {missing[0].replace('_', ' ')}?"
                    else:
                        return "Please enter your date of birth in the format YYYY-MM-DD."
                
                # Generic field handler
                await self._update_field(context["user_id"], field, message)
                missing = await self._get_missing_fields(context["user_id"])
                
                if not missing:
                    context["profile_complete"] = True
                    context["awaiting_profile_field"] = False
                    return "🎉 Your profile is now complete! Let's collect your CGM readings next. Please enter your blood sugar readings separated by commas."
                
                context["field_to_update"] = missing[0]
                return f"Thanks! What's your {missing[0].replace('_', ' ')}?"
            
            # First time greeting - check profile and start collecting
            profile_info = await self._get_profile(context["user_id"])
            if profile_info.get("first_name"):
                greeting = f"Hello {profile_info['first_name']}! 👋 "
            else:
                greeting = "Hello! 👋 "
            
            missing = await self._get_missing_fields(context["user_id"])
            if not missing:
                context["profile_complete"] = True
                return f"{greeting}Your profile is complete! Let's collect your CGM readings. Please enter your blood sugar readings separated by commas."
            
            context["awaiting_profile_field"] = True
            context["field_to_update"] = missing[0]
            return f"{greeting}I need to collect some information to personalize your experience. What's your {missing[0].replace('_', ' ')}?"
        
        # 3. CGM Phase
        if not context.get("cgm_collected", False):
            # If awaiting CGM readings
            if context.get("awaiting_cgm", False):
                # Check if message contains valid readings
                try:
                    readings = [float(r.strip()) for r in message.split(",")]
                    if all(70 <= r <= 180 for r in readings):
                        # Store readings in DB
                        for reading in readings:
                            await self._add_cgm_reading(context["user_id"], reading)
                        
                        context["cgm_collected"] = True
                        context["awaiting_cgm"] = False
                        return "Thanks for providing your CGM readings! I can now generate a personalized meal plan for you. Type 'plan' to see your meal recommendations."
                    else:
                        return "Some readings seem outside the normal range (70-180 mg/dL). Please verify and enter again, or type 'skip' to continue."
                except ValueError:
                    return "I couldn't understand those readings. Please enter numbers separated by commas (e.g., 95, 110, 102)."
            else:
                # Start CGM collection
                context["awaiting_cgm"] = True
                return "Now, I need your recent blood sugar readings to personalize your meal plan. Please enter your CGM readings separated by commas (e.g., 95, 110, 102)."
        
        # 4. Meal Planning Phase
        name = (await self._get_profile(context["user_id"])).get("first_name", "")
        pref = (await self._get_profile(context["user_id"])).get("dietary_preference", "")
        
        # Check for new CGM readings request
        cgm_keywords = ["cgm", "reading", "glucose", "blood sugar", "rating"]
        update_keywords = ["new", "update", "add", "enter", "record"]
        
        is_cgm_update_request = any(k in message.lower() for k in cgm_keywords) and \
                             (any(k in message.lower() for k in update_keywords) or \
                              any(str(num) in message for num in range(10)))
        
        if is_cgm_update_request:
            try:
                # Try to extract numeric values from the message
                import re
                numbers = re.findall(r'\d+\.?\d*', message)
                if numbers:
                    readings = [float(num) for num in numbers]
                    # Store readings in DB
                    for reading in readings:
                        await self._add_cgm_reading(context["user_id"], reading)
                    
                    return f"Thanks for the updated CGM reading{'s' if len(readings) > 1 else ''}! I've recorded {', '.join([str(r) for r in readings])}. This will help me provide a more accurate meal plan. Type 'plan' to see your updated recommendations."
                else:
                    # No numbers found, prompt for specific readings
                    context["awaiting_cgm"] = True
                    return "I'd be happy to update your CGM readings. Please provide your blood sugar readings separated by commas (e.g., 95, 110, 102)."
            except ValueError:
                context["awaiting_cgm"] = True
                return "I couldn't understand those readings. Please enter numbers separated by commas (e.g., 95, 110, 102)."
        
        # Generate a mock meal plan based on the user's dietary preference
        if "plan" in message.lower():
            return self._generate_meal_plan(name, pref)
        
        # Default response when none of the specific intents are detected
        return f"Hi {name}! Your profile is complete and I have your CGM readings. \n\nYou can:\n- Type 'plan' to generate your personalized meal plan\n- Enter new CGM readings (e.g., 'My new reading is 120')\n- Type 'status' to check your profile information"
    
    async def _get_profile(self, user_id: int) -> dict:
        """Get user profile from the database."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM users WHERE id = ?
            """, (user_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return {}
        except Exception:
            return {}
    
    async def _get_missing_fields(self, user_id: int) -> list:
        """Get list of missing required fields for a user."""
        profile = await self._get_profile(user_id)
        required_fields = ["first_name", "last_name", "city", "date_of_birth", "dietary_preference"]
        
        # Return fields that are empty or None
        return [field for field in required_fields if not profile.get(field)]
    
    async def _update_field(self, user_id: int, field: str, value: str) -> None:
        """Update a field in the user profile."""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Update the field
            cursor.execute(f"UPDATE users SET {field} = ? WHERE id = ?", (value, user_id))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error updating field: {e}")
    
    async def _add_cgm_reading(self, user_id: int, reading: float) -> None:
        """Add a CGM reading to the database."""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Insert the reading
            cursor.execute("""
                INSERT INTO cgm_readings (user_id, reading, reading_type, timestamp)
                VALUES (?, ?, ?, ?)
            """, (user_id, reading, "fingerstick", datetime.datetime.now()))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error adding CGM reading: {e}")
    
    def _generate_meal_plan(self, name: str, dietary_preference: str) -> str:
        """Generate a mock meal plan based on dietary preference."""
        greeting = f"# Personalized Meal Plan for {name}\n\n"
        
        if dietary_preference.lower() == "vegetarian":
            plan = """## Breakfast
- Veggie omelette with spinach, tomatoes, and feta cheese
- Whole grain toast with avocado
- Fresh berries

## Lunch
- Quinoa salad with roasted vegetables
- Greek yogurt with honey
- Apple slices

## Dinner
- Lentil soup with vegetables
- Mixed green salad with olive oil dressing
- Brown rice

## Snacks
- Hummus with carrot sticks
- Mixed nuts
- Cottage cheese with fruit

*This meal plan is designed to help regulate your blood sugar levels based on your CGM readings and vegetarian preference.*"""
        
        elif dietary_preference.lower() == "vegan":
            plan = """## Breakfast
- Overnight oats with almond milk, chia seeds, and berries
- Plant-based yogurt with granola
- Fresh fruit

## Lunch
- Buddha bowl with quinoa, roasted chickpeas, and vegetables
- Avocado toast on whole grain bread
- Orange slices

## Dinner
- Lentil and vegetable curry
- Brown rice
- Steamed broccoli

## Snacks
- Almond butter with apple slices
- Trail mix with dried fruits and nuts
- Edamame beans

*This meal plan is designed to help regulate your blood sugar levels based on your CGM readings and vegan preference.*"""
        
        else:  # non-vegetarian
            plan = """## Breakfast
- Scrambled eggs with turkey sausage
- Whole grain toast with avocado
- Fresh berries

## Lunch
- Grilled chicken salad with mixed greens
- Quinoa side
- Apple slices

## Dinner
- Baked salmon with lemon and herbs
- Steamed vegetables
- Brown rice

## Snacks
- Greek yogurt with honey
- Mixed nuts
- Cottage cheese with fruit

*This meal plan is designed to help regulate your blood sugar levels based on your CGM readings and non-vegetarian preference.*"""
        
        return greeting + plan


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
        name = f"{user['first_name'] or ''} {user['last_name'] or ''}".strip()
        print(f"ID: {user['id']}, Name: {name}, Email: {user['email'] or ''}")
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
    
    print(f"\n{COLORS['CYAN']}Starting chat with Aduro AI Health Assistant (Demo Mode)...{COLORS['RESET']}")
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
    orchestrator = MockOrchestrator()
    
    while True:
        print(f"\n{COLORS['BOLD']}Aduro AI Health Assistant (Demo Mode){COLORS['RESET']}")
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
        print(f"\n{COLORS['BOLD']}Aduro AI Health Assistant - Demo Mode{COLORS['RESET']}")
        print("This is a demonstration of the Aduro AI system with mocked agent behaviors.")
        print("It shows the flow between profile management, CGM collection, and meal planning.")
        
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
