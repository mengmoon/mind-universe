import nltk
from nltk.sentiment import SentimentIntensityAnalyzer
nltk.download('vader_lexicon', quiet=True)

def analyze_journal(text):
    sia = SentimentIntensityAnalyzer()
    score = sia.polarity_scores(text)
    flags = []
    archetypes = []
    maslow_needs = []
    strengths = []
    distortions = []

    # Sentiment and symptom flags
    if score['compound'] < -0.5:
        flags.append("helplessness")
        maslow_needs.append("Esteem: low confidence")
        distortions.append("All-or-nothing thinking")
    if "voices" in text.lower():
        flags.append("hallucination")
        maslow_needs.append("Safety: need for stability")
        archetypes.append("Shadow: symbolic expression")
    if "lonely" in text.lower():
        maslow_needs.append("Love/Belonging: need for connection")
    if "try" in text.lower():
        strengths.append("Hope: effort detected")
    if "worthless" in text.lower():
        distortions.append("Catastrophizing")

    return {
        "score": score,
        "flags": flags,
        "archetypes": archetypes,
        "maslow_needs": maslow_needs,
        "strengths": strengths,
        "distortions": distortions,
        "suggestions": [
            f"Freudian: Reflect on {distortions[0] if distortions else 'triggers'}—journal unconscious thoughts.",
            f"Adlerian: Build social interest—connect with one person.",
            f"Jungian: Visualize {'Shadow dialogue' if 'Shadow' in archetypes else 'Hero self'} for empowerment.",
            f"Maslow: Address {maslow_needs[0] if maslow_needs else 'basic needs'}—try a routine.",
            f"Positive Psychology: Practice gratitude—list 3 things you're thankful for.",
            f"CBT: Challenge {distortions[0] if distortions else 'negative thoughts'}—list 3 counter-evidences."
        ]
    }