"""
Meal Planner Agent for generating personalized meal plans based on user profile and CGM data.
"""

from datetime import datetime, date
from typing import Dict, List, Optional, TypedDict, Any
# Import needed for validate_meal_plan function
import re
import sqlite3
from pathlib import Path

from agents import Agent, Runner, function_tool

# Constants
DB_PATH = Path("db/users.db")
DEFAULT_DAYS = 7
MIN_READINGS = 3

# Type Definitions
class CGMReading(TypedDict):
    reading: float
    timestamp: str  # Changed to string to avoid serialization issues

class UserProfile(TypedDict):
    first_name: str
    dietary_preference: str  # "vegetarian" | "non-vegetarian" | "vegan"
    medical_conditions: Optional[str]
    physical_limitations: Optional[str]
    date_of_birth: date
    created_at: datetime

# System Prompt
SYSTEM_PROMPT = """
You are a clinical dietitian assistant. You must produce a 3-meal plan (breakfast, lunch, dinner) for the next 24 hours that:
- Matches the user's dietary_preference (vegetarian/non-veg/vegan).
- Respects medical_conditions and physical_limitations.
- Targets a daily calorie goal of ±10% (derive from BMR if absent).
- Smooths post-prandial CGM spikes to keep readings ≤30 mg/dL above baseline.
- Includes per-meal macros: kcal, carbs, protein, fats.
- Presents output as Markdown with headings ("## Breakfast") and bullet details.
"""

def get_db_connection() -> sqlite3.Connection:
    """Create and return a database connection."""
    return sqlite3.connect(DB_PATH)

# Get a database connection
def get_user_profile(user_id: int) -> Dict[str, Any]:
    """
    Fetch user profile from the database.
    
    Args:
        user_id: The ID of the user
        
    Returns:
        Dict containing user profile information
        
    Raises:
        ValueError: If user not found or profile is incomplete
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT first_name, dietary_preference, medical_conditions, 
                   physical_limitations, date_of_birth, created_at
            FROM users 
            WHERE id = ?
            """,
            (user_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            raise ValueError(f"User with ID {user_id} not found")
            
        profile = {
            "first_name": result[0],
            "dietary_preference": result[1].lower() if result[1] else None,
            "medical_conditions": result[2],
            "physical_limitations": result[3],
            "date_of_birth": result[4],
            "created_at": result[5]
        }
        
        # Validate required fields
        if not profile["dietary_preference"] or profile["dietary_preference"] not in ["vegetarian", "non-vegetarian", "vegan"]:
            raise ValueError("Dietary preference is missing or invalid. Please update your profile.")
            
        return profile
    finally:
        conn.close()


def get_recent_cgm(user_id: int, days: int = DEFAULT_DAYS) -> List[CGMReading]:
    """
    Fetch recent CGM readings for a user.
    
    Args:
        user_id: The ID of the user
        days: Number of days to look back for readings (default: 7)
        
    Returns:
        List of CGM readings with timestamps
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT reading, timestamp
            FROM cgm_readings
            WHERE user_id = ? 
            AND timestamp >= datetime('now', ? || ' days')
            ORDER BY timestamp ASC
            """,
            (user_id, f"-{days}")
        )
        return [
            {"reading": row[0], "timestamp": row[1]}
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


@function_tool
async def validate_meal_plan(meal_plan: str) -> bool:
    """
    Validate a personalized meal plan.
    
    Args:
        meal_plan: The meal plan to validate
        
    Returns:
        True if the meal plan is valid, False otherwise
    """
    # TO DO: implement meal plan validation logic
    return True


@function_tool
async def generate_meal_plan(user_id: int) -> str:
    """
    Generate a personalized meal plan for the user.
    
    Args:
        user_id: The ID of the user
        
    Returns:
        A string containing the formatted meal plan
    """
    # Validate user_id
    if not isinstance(user_id, int) or user_id <= 0:
        return "⚠️ Sorry, I couldn't find your user ID. Please re-authenticate."
    
    try:
        # Get user profile and CGM data
        profile = get_user_profile(user_id)
        cgm_data = get_recent_cgm(user_id)
        
        # Check for sufficient CGM data
        if len(cgm_data) < 3:  # Minimum 3 readings required
            return (
                f"I only see {len(cgm_data)} readings in the last {DEFAULT_DAYS} days. "
                "More data helps me create a better plan. Please add more readings."
            )
        
        # Create meal plan content with user information
        meal_plan = f"# Personalized Meal Plan for {profile['first_name']}\n\n"
        
        # Add dietary information
        meal_plan += "## Dietary Information\n"
        meal_plan += f"- Preference: {profile['dietary_preference']}\n"
        if profile.get('medical_conditions'):
            meal_plan += f"- Medical Conditions: {profile['medical_conditions']}\n"
        if profile.get('physical_limitations'):
            meal_plan += f"- Physical Limitations: {profile['physical_limitations']}\n"
        
        # Add CGM summary
        meal_plan += "\n## CGM Data Summary\n"
        meal_plan += f"- {len(cgm_data)} readings from the past {DEFAULT_DAYS} days\n"
        if cgm_data:
            avg_reading = sum(reading['reading'] for reading in cgm_data) / len(cgm_data)
            meal_plan += f"- Average reading: {avg_reading:.1f} mg/dL\n"
            
        # Add meal sections
        meal_plan += "\n## Breakfast\n"
        meal_plan += "Oatmeal with berries and nuts\n"
        meal_plan += "- Calories: 350 kcal\n"
        meal_plan += "- Carbs: 45g\n"
        meal_plan += "- Protein: 12g\n"
        meal_plan += "- Fat: 15g\n"
        
        meal_plan += "\n## Lunch\n"
        meal_plan += "Quinoa salad with vegetables\n"
        meal_plan += "- Calories: 450 kcal\n"
        meal_plan += "- Carbs: 60g\n"
        meal_plan += "- Protein: 15g\n"
        meal_plan += "- Fat: 18g\n"
        
        meal_plan += "\n## Dinner\n"
        meal_plan += "Grilled fish with roasted vegetables\n"
        meal_plan += "- Calories: 500 kcal\n"
        meal_plan += "- Carbs: 40g\n"
        meal_plan += "- Protein: 30g\n"
        meal_plan += "- Fat: 25g\n"
        
        meal_plan += "\n## Snacks\n"
        meal_plan += "Greek yogurt with honey\n"
        meal_plan += "- Calories: 200 kcal\n"
        meal_plan += "- Carbs: 25g\n"
        meal_plan += "- Protein: 10g\n"
        meal_plan += "- Fat: 8g\n"
        
        return f"👍 Here's your personalized meal plan for the next 24 hours.\n\n{meal_plan}"
        
    except ValueError as e:
        return f"⚠️ {str(e)}"
    except Exception as e:
        return f"Error generating meal plan: {str(e)}"


class MealPlanner(Agent):
    """Agent for generating personalized meal plans based on user profile and CGM data."""
    
    def __init__(self):
        super().__init__(
            name="meal_planner",
            instructions=SYSTEM_PROMPT,
            tools=[generate_meal_plan]
        )


# Create a singleton instance
meal_planner_agent = MealPlanner()

# Example usage
if __name__ == "__main__":
    import asyncio
    import os
    from dotenv import load_dotenv
    
    async def main():
        # Load environment variables
        load_dotenv()
        
        # Check for required environment variables
        if not os.getenv("OPENAI_API_KEY"):
            print("Error: OPENAI_API_KEY environment variable is not set.")
            print("Please create a .env file with your OpenAI API key.")
            return
        
        try:
            # Initialize the agent
            print("Initializing Meal Planner agent...")
            meal_planner = MealPlanner()
            
            # Example usage with a test user ID
            user_id = 1  # Replace with actual user ID
            print(f"Generating meal plan for user ID: {user_id}")
            
            # Generate meal plan using the function tool
            response = await Runner.run(meal_planner, f"Generate a meal plan for me with user ID {user_id}")
            meal_plan = response.final_output
            print("\n" + "="*70)
            print(meal_plan)
            print("="*70)
            
        except Exception as e:
            print(f"An error occurred: {str(e)}")
    
    # Run the async main function
    asyncio.run(main())
