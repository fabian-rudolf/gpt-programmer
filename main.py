import sqlite3
import inspect
import openai
import json
import warnings
import sys
from io import StringIO
import contextlib

def setup_database(drop_functions_table_if_exists=False):
    """Setup SQLite database for function storage"""
    # SQLite database setup
    conn = sqlite3.connect('functions.db')
    cursor = conn.cursor()
    if drop_functions_table_if_exists:
        cursor.execute("""
        DROP TABLE IF EXISTS functions
        """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS functions (
        name TEXT PRIMARY KEY,
        code TEXT NOT NULL,
        language TEXT NOT NULL
    )
    """)
    return conn, cursor

def define_function(name: str, code: str):
    exec(code, globals())
    print(f"Function '{name}' loaded from database")

def list_functions(cursor, conn):
    """List all function names in the SQLite database."""
    cursor.execute("SELECT name FROM functions")
    result = cursor.fetchall()

    if result is None:
        print("No functions found in the database.")
    else:
        function_names = [row[0] for row in result]
        print("Function names in the database:")
        for name in function_names:
            print(name)

def show_function(name, cursor, conn):
    """Display a function's details from the SQLite database."""
    cursor.execute("SELECT * FROM functions WHERE name=?", (name,))
    result = cursor.fetchone()

    if result is None:
        print(f"No function named {name} found in the database.")
    else:
        print(f"Function name: {result[0]}")
        print("Code:")
        print(result[1])

def register_function(name, code, language, cursor, conn):
    """Save a function's code into the SQLite database."""
    user_input = input(f"Do you want to register the function '{name}'? (yes/no)\n> ")
    if user_input.lower() == 'yes':
        cursor.execute("INSERT OR REPLACE INTO functions VALUES (?, ?, ?)", (name, code, language))
        conn.commit()

        print(f"Function '{name}' saved to database")

        if language.lower() == 'python':
            print("Would you like to load the function in-memory for execution? (yes/no)")
            user_input = input("> ")
            if user_input.lower() == "yes":
                define_function(name, code)
    else:
        print(f"Function '{name}' registration cancelled")
        offer_fix(name, code, cursor, conn)

def request_function(cursor, conn):
    """Request a function's details from the user, generate it, and register it."""
    instruction = input("What should the function do? (describe in one sentence)\n> ")

    print(f"Generating function...")

    code, function_name, language = generate_code(instruction)

    register_function(function_name, code, language, cursor, conn)

def get_function(name, cursor, conn):
    """Retrieve a function from the SQLite database."""
    cursor.execute("SELECT code FROM functions WHERE name=?", (name,))
    result = cursor.fetchone()

    if result is None:
        print(f"No function named {name} found in the database.")
        user_input = input("Do you want to generate a new function named {}? (yes/no)\n> ".format(name))
        if user_input.lower() == "yes":
            request_function(cursor, conn)
        else:
            raise ValueError(f"No function named {name} found in the database.")
    return result[0]

def extract_code(reply_content):
    """Extracts the function code, function name, and language from the reply content dictionary"""
    function_call = reply_content.get('function_call')
    if function_call:
        function_args_str = function_call.get('arguments')
        if function_args_str:
            try:
                function_args = json.loads(function_args_str)
                code = function_args.get('function_code')
                function_name = function_args.get('function_name')
                language = function_args.get('function_language')
                return code, function_name, language
            except Exception as e:
                warnings.warn(f"Failed to extract function details. Exception: {str(e)}\nInput: {function_args_str}")
                return None, None, None
    warnings.warn("Warning: The function could not be generated. Please try again.")
    return None, None, None

def generate_code(instruction, existing_code=None):
    """Generate Python code using OpenAI GPT-4."""
    instruction = instruction + "\n" + existing_code if existing_code else instruction
    completion = openai.ChatCompletion.create(
        model="gpt-4-0613", 
        messages=[{"role": "user", "content": instruction}],
        functions=[ 
            { 
                "name": "execute_code", 
                "description": "Executes code passed as parameter to achieve input prompt in natural language", 
                "parameters": { 
                    "type": "object", 
                    "properties": {
                        "function_code": {
                            "type": "string", 
                            "description": "The non-nullable complete standalone best-practice commented documented function definition code including a function header with typed parameters and the function body with a return type, error handling and a docstring" 
                        },
                        "function_name": {
                            "type": "string", 
                            "description": "A non-nullable speaking identifier as the name of the given code function in the naming convention of the programming language"
                        },
                        "function_language": {
                            "type": "string", 
                            "description": "The non-nullable programming language of the generated code. Defaults to python"
                        }
                    }, 
                    "required": ["function_code", "function_name", "function_language"] 
                } 
            }
        ], 
        function_call={"name": "execute_code"},
    )
    reply_content = completion.choices[0].message

    code, function_name, language = extract_code(reply_content)

    print(f"Generation result:")
    print(f"Function name: {function_name}")
    print(f"Code:\n---\n{code}\n---")
    print(f"Language: {language}")

    return code, function_name, language

def fix_function(name, existing_code, cursor, conn):
    """Request a function's details from the user, generate new code, and register it."""
    print(f"Fixing function '{name}'.")

    user_input = input("How should the function be changed?\n> ")

    instruction = f"The following code has issues and needs to be fixed: \n{existing_code}\nPlease generate an improved version. {user_input}"
    
    code, function_name, language = generate_code(instruction)

    if code:    
        register_function(function_name, code, language, cursor, conn)
    else:
        print("Unable to generate the corrected code. Please try again.")

@contextlib.contextmanager
def stdoutIO(stdout=None):
    old = sys.stdout
    if stdout is None:
        stdout = StringIO()
    sys.stdout = stdout
    yield stdout
    sys.stdout = old

def execute_user_code(user_code):
    """Execute user code to call functions previously loaded from the SQLite database."""
    with stdoutIO() as s:
        try:
            exec(user_code, globals())
        except Exception as e:
            print(f"Execution of '{user_code}' yielded error: {str(e)}")
            print("Please try again")
    print("\n---\nOutput:\n", s.getvalue())
    print("---\nExecution finished")

def offer_fix(name, existing_code, cursor, conn):
    print("Would you like to apply changes? (yes/no)")
    user_input = input("> ")
    if user_input.lower() == "yes":
        fix_function(name, existing_code, cursor, conn)

def start_agent(cursor, conn):
    """Starts the AI agent."""
    print("Metaprogrammer started")

    while True:
        print("Waiting for instruction (generate/load/execute/list/show)")
        user_input = input("> ")

        if user_input.lower() == "exit":
            print("Goodbye!")
            break

        elif user_input.lower() == "generate":
            request_function(cursor, conn)

        elif user_input.lower() == "execute":
            user_code = input("Enter the code you want to execute?\n>>> ")

            try:
                execute_user_code(user_code)
            except ValueError as e:
                print(str(e))

        elif user_input.lower() == "load":
            function_name = input("Enter the function name you want to load from the database\n>>> ")
            function_code = get_function(function_name, cursor, conn)
            define_function(function_name, function_code)

        elif user_input.lower() == "list":
            list_functions(cursor, conn)

        elif user_input.lower() == "show":
            function_name = input("What is the name of the function you want to display?\n> ")
            show_function(function_name, cursor, conn)

        else:
            print("I'm sorry, I didn't understand your command. Please, try again.")

def main():
    conn, cursor = setup_database()
    start_agent(cursor, conn)

if __name__ == "__main__":
    main()
