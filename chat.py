import ollama

def psychodynamic_chat(user_input):
    prompt = f"""
    Analyze '{user_input}' for schizoaffective symptoms or life goals.
    Respond with:
    1. Freudian: Identify defenses (e.g., projection) and suggest introspective coping.
    2. Adlerian: Suggest social interest or 'act as if' tasks.
    3. Jungian: Identify archetypes (e.g., Shadow, Hero) and active imagination.
    4. Maslow: Assess unmet needs (physiological, safety, belonging, esteem, self-actualization).
    5. Positive Psychology: Identify strengths (e.g., hope) and suggest gratitude/mindfulness.
    6. CBT: Identify distortions (e.g., all-or-nothing) and suggest cognitive restructuring or behavioral activation.
    """
    try:
        response = ollama.chat(model='llama3', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
    except Exception as e:
        return f"Error: {str(e)}. Try again or check Ollama."