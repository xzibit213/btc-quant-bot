import os
import sys
import argparse
from zhipuai import ZhipuAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

API_KEY = os.getenv("ZHIPUAI_API_KEY")
if not API_KEY:
    print("Error: ZHIPUAI_API_KEY environment variable not set. Please add it to your .env file.")
    sys.exit(1)

client = ZhipuAI(api_key=API_KEY)

def generate_code(prompt, output_file):
    print(f"Assigning task to GLM-4-Flash...\nTask: {prompt}\nTarget Output: {output_file}")
    print("Awaiting response from worker node...")
    
    system_prompt = (
        "You are a master coder, acting as a subordinate worker node. "
        "Your task is to write code based on the exact specifications provided by the Architect. "
        "CRITICAL INSTRUCTION: Return ONLY the raw code. Do NOT wrap your response in markdown code blocks (e.g., ```python). "
        "Do NOT include any explanations, greetings, or conversational text. Your entire output will be written directly to a file and executed. "
        "Output raw, executable code only."
    )
    
    # Load shared skills and memory for GLM
    shared_memory_path = r"C:\Users\DELL\.gemini\antigravity\knowledge\glm_skills.md"
    if os.path.exists(shared_memory_path):
        with open(shared_memory_path, "r", encoding="utf-8") as sm_file:
            system_prompt += "\n\n=== SHARED SKILLS AND MEMORY ===\n" + sm_file.read()
    
    try:
        response = client.chat.completions.create(
            model="glm-4-flash",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Low temperature for highly deterministic code generation
            max_tokens=4095
        )
        
        result = response.choices[0].message.content
        
        # Fallback to strip markdown if the model hallucinates formatting
        if result.startswith("```"):
            lines = result.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            result = "\n".join(lines)
            
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(result)
            
        print(f"[SUCCESS] Code written to {output_file}")
        
    except Exception as e:
        print(f"[ERROR] Error communicating with GLM API: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GLM Worker Agent for bulk coding tasks.")
    parser.add_argument("prompt", help="The exact instructions for the code to generate.")
    parser.add_argument("--output", required=True, help="The file path to save the generated code.")
    
    args = parser.parse_args()
    generate_code(args.prompt, args.output)
