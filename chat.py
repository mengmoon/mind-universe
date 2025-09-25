try:
    import ollama
    def psychodynamic_chat(user_input):
        # Ollama-based chat logic (used locally)
        response = ollama.chat(model='llama3', messages=[{'role': 'user', 'content': user_input}])
        return response['message']['content']
except ImportError:
    import nltk
    from nltk.sentiment.vader import SentimentIntensityAnalyzer
    nltk.download('vader_lexicon')
    def psychodynamic_chat(user_input):
        # Fallback using NLTK for sentiment-based psychodynamic analysis
        sid = SentimentIntensityAnalyzer()
        scores = sid.polarity_scores(user_input)
        sentiment = "positive" if scores['compound'] > 0 else "negative" if scores['compound'] < 0 else "neutral"
        
        # Psychodynamic response based on sentiment
        response = f"Analysis of '{user_input}':\n"
        # 1. Freudian
        response += "1. Freudian: You might be using projection to externalize feelings. Try introspective journaling to explore unconscious emotions.\n"
        # 2. Adlerian
        response += "2. Adlerian: Connect with a friend or community to foster social interest. Act as if you feel confident today.\n"
        # 3. Jungian
        response += "3. Jungian: Your input reflects the Shadow archetype (hidden struggles). Try active imagination: visualize a conversation with this part of yourself.\n"
        # 4. Maslow
        response += "4. Maslow: You may have unmet belonging or esteem needs. Focus on small goals to build self-actualization, like a daily gratitude practice.\n"
        # 5. Positive Psychology
        response += f"5. Positive Psychology: Your strength of hope shines through. Practice mindfulness or list three things you're grateful for.\n"
        # 6. CBT
        response += f"6. CBT: Watch for all-or-nothing thinking (e.g., 'I always fail'). Restructure by noting one success today, like journaling.\n"
        return response