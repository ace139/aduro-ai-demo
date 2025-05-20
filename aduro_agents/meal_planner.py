"""
Meal Planner Agent for generating personalized meal plans based on user profile and CGM data.

This module provides the MealPlanner agent which is responsible for:
- Generating personalized meal plans based on user preferences
- Analyzing CGM data for dietary recommendations
- Providing nutritional guidance based on user health profile
"""

from typing import Dict, List, Optional, TypedDict, Any
import sqlite3
from pathlib import Path

from agents import Agent, function_tool
from typing_extensions import Literal

# Constants
DB_PATH = Path(__file__).resolve().parent.parent / "db" / "users.db"
DEFAULT_DAYS = 7
MIN_READINGS = 3

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

# Type Definitions
DietaryPreference = Literal["vegetarian", "non-vegetarian", "vegan"]

class CGMReading(TypedDict):
    """Represents a single CGM reading with timestamp."""
    reading: float
    timestamp: str  # ISO format datetime string

class UserProfile(TypedDict):
    """Represents a user's profile information relevant to meal planning."""
    first_name: str
    last_name: str
    dietary_preference: DietaryPreference
    medical_conditions: Optional[str]
    physical_limitations: Optional[str]

class MealPlan(TypedDict):
    """Represents a generated meal plan for a user."""
    id: int
    user_id: int
    plan_date: str  # ISO format date string
    meals: Dict[str, List[Dict[str, Any]]]  # meal_type: [food_items]
    nutritional_info: Dict[str, float]
    created_at: str  # ISO format datetime string

# Database Helper Functions
async def _get_user_profile(user_id: int, test_conn=None) -> Optional[UserProfile]:
    """
    Retrieve a user's profile from the database.
    
    Args:
        user_id: The ID of the user
        test_conn: Optional database connection for testing
        
    Returns:
        UserProfile if found, None otherwise
    """
    close_conn = False
    if test_conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        close_conn = True
    else:
        conn = test_conn
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT first_name, last_name, dietary_preference, 
                   medical_conditions, physical_limitations
            FROM users 
            WHERE id = ?
        """, (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
            
        # Access columns by index since we're not using row_factory=sqlite3.Row
        return {
            "first_name": row[0],
            "last_name": row[1],
            "dietary_preference": row[2],
            "medical_conditions": row[3],
            "physical_limitations": row[4]
        }
    finally:
        if close_conn:
            conn.close()

async def _get_recent_cgm_readings(user_id: int, days: int = 7, test_conn=None) -> List[CGMReading]:
    """
    Retrieve recent CGM readings for a user.
    
    Args:
        user_id: The ID of the user
        days: Number of days of readings to retrieve
        test_conn: Optional database connection for testing
        
    Returns:
        List of CGM readings with timestamps
    """
    close_conn = False
    if test_conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        close_conn = True
    else:
        conn = test_conn
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT reading, timestamp 
            FROM cgm_readings 
            WHERE user_id = ? 
            AND timestamp >= datetime('now', ? || ' days')
            ORDER BY timestamp DESC
        """, (user_id, f"-{days}"))
        
        return [
            {"reading": row[0], "timestamp": row[1]}
            for row in cursor.fetchall()
        ]
    finally:
        if close_conn:
            conn.close()

# Tool Definitions
@function_tool
async def generate_meal_plan(
    user_id: int,
    days: int = 7,
    dietary_preference: Optional[DietaryPreference] = None,
    test_conn=None
) -> Dict[str, Any]:
    """
    Generate a personalized meal plan for a user based on their profile and CGM data.
    
    Args:
        user_id: The ID of the user
        days: Number of days to generate the meal plan for (default: 7)
        dietary_preference: Optional override for dietary preference
        test_conn: Optional database connection for testing
        
    Returns:
        Dictionary containing the generated meal plan
    """
    # Input validation
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("Invalid user ID")
    
    if not isinstance(days, int) or days <= 0 or days > 30:
        raise ValueError("Days must be between 1 and 30")
    
    # Get user profile
    profile = await _get_user_profile(user_id, test_conn)
    if not profile:
        raise ValueError(f"User with ID {user_id} not found")
    
    # Get recent CGM readings
    cgm_readings = await _get_recent_cgm_readings(user_id, days, test_conn)
    
    # Use provided preference or fall back to user's preference
    dietary_preference = dietary_preference or profile["dietary_preference"]
    
    # TODO: Implement actual meal plan generation logic based on profile and CGM data
    # For now, return a placeholder plan
    return {
        "user_id": user_id,
        "days": days,
        "dietary_preference": dietary_preference,
        "cgm_readings_count": len(cgm_readings),
        "message": "Meal plan generation will be implemented here"
    }

class MealPlanner(Agent):
    """
    Agent for generating personalized meal plans based on user profile and CGM data.
    
    This agent helps users by:
    - Creating customized meal plans based on dietary preferences
    - Analyzing CGM data for personalized recommendations
    - Providing nutritional guidance and meal suggestions
    - Adapting plans based on user feedback and health data
    """

    def __init__(self):
        """Initialize the MealPlanner agent with its instructions and tools."""
        super().__init__(
            name="meal_planner",
            instructions=SYSTEM_PROMPT,
            tools=[generate_meal_plan],
        )
    
    async def process_input(
        self, 
        message: str, 
        context: Optional[Dict[str, Any]] = None,
        test_conn=None
    ) -> str:
        """
        Process user input and generate a response using the agent's tools.
        
        Args:
            message: The user's message
            context: Optional context dictionary (should contain 'user_id')
            test_conn: Optional database connection for testing
            
        Returns:
            The agent's response as a string
        """
        context = context or {}
        user_id = context.get('user_id')
        
        if not user_id or not isinstance(user_id, int):
            return "Error: Authentication required. Please provide a valid user_id."
        
        try:
            # Let the agent handle the message using its tools
            response = await self.run(message, context={"user_id": user_id})
            return str(response)
        except Exception as e:
            return f"Error generating meal plan: {str(e)}"

    @staticmethod
    def _get_db_connection() -> sqlite3.Connection:
        """Create and return a database connection."""
        # Ensure that date/datetime types are parsed correctly from the database
        return sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)

    def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        """
        Fetch user profile from the database.
        
        Args:
            user_id: The ID of the user
            
        Returns:
            Dict containing user profile information
            
        Raises:
            ValueError: If user not found or profile is incomplete
        """
        conn = self._get_db_connection()
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
                
            profile: UserProfile = { # Added type hint here for clarity
                "first_name": result[0],
                "dietary_preference": result[1].lower() if result[1] else None,
                "medical_conditions": result[2],
                "physical_limitations": result[3],
                "date_of_birth": result[4], # Expects date object
                "created_at": result[5]    # Expects datetime object
            }
            
            # Validate required fields
            if not profile["dietary_preference"] or profile["dietary_preference"] not in ["vegetarian", "non-vegetarian", "vegan"]:
                raise ValueError("Dietary preference is missing or invalid. Please update your profile.")
                
            return profile
        finally:
            conn.close()

    def get_recent_cgm(self, user_id: int, days: int = DEFAULT_DAYS) -> List[CGMReading]:
        """
        Fetch recent CGM readings for a user.
        
        Args:
            user_id: The ID of the user
            days: Number of days to look back for readings (default: 7)
            
        Returns:
            List of CGM readings with timestamps
        """
        conn = self._get_db_connection()
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
                {"reading": row[0], "timestamp": str(row[1])} # Ensure timestamp is string
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    @staticmethod
    def validate_meal_plan(meal_plan: str) -> bool:
        """
        Validate a personalized meal plan.
        
        Args:
            meal_plan: The meal plan to validate
            
        Returns:
            True if the meal plan is valid, False otherwise
        """
        # TO DO: implement meal plan validation logic
        return True





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
            
            # Generate meal plan using the agent's process_input method
            response = await meal_planner.process_input(
                "Generate a meal plan for me",
                context={"user_id": user_id}
            )
            print("\n" + "="*70)
            print(response)
            print("="*70)
            
        except Exception as e:
            print(f"An error occurred: {str(e)}")
    
    # Run the async main function
    asyncio.run(main())
