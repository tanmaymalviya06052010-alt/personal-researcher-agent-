import os
import requests
import json
from flask import Flask, render_template, request, jsonify, session
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

def search_google(query, num_results=10):
    if not SERPER_API_KEY:
        return {"error": "Serper API key not configured"}
    
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"q": query, "num": num_results}
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        results = []
        for item in data.get("organic", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "link": item.get("link", "")
            })
        return results
    return {"error": f"Search failed: {response.status_code} - {response.text}"}

def get_llm_response(prompt):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://research-bot.render.com",
        "X-Title": "ResearchBot"
    }
    payload = {
        "model": "nvidia/llama-3.1-nemotron-70b-instruct",
        "messages": [
            {"role": "system", "content": "You are a helpful research assistant. Provide clear, well-structured answers in a friendly tone."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 2000
    }
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    return f"Error: {response.status_code} - {response.text}"

def generate_report(query, search_results):
    search_text = "\n\n".join([
        f"Source {i+1}: {r['title']}\n{r['snippet']}\nLink: {r['link']}"
        for i, r in enumerate(search_results)
    ])
    
    prompt = f"""Based on the user's request: "{query}"

Here are the search results from Google:
{search_text}

Please create a clean, well-organized research report with:
1. A brief summary at the top
2. Key findings as bullet points
3. Useful resources/links
4. Any recommendations if applicable

Format it nicely for the user to read."""
    
    return get_llm_response(prompt)

@app.route("/")
def index():
    if "messages" not in session:
        session["messages"] = []
    return render_template("index.html", messages=session["messages"])

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message", "").strip()
    
    if not user_message:
        return jsonify({"error": "Please enter a message"})
    
    if "messages" not in session:
        session["messages"] = []
    
    session["messages"].append({"role": "user", "content": user_message, "time": datetime.now().strftime("%H:%M")})
    
    search_results = search_google(user_message)
    
    if isinstance(search_results, dict) and "error" in search_results:
        session["messages"].append({"role": "bot", "content": f"⚠️ {search_results['error']}", "time": datetime.now().strftime("%H:%M")})
        session.modified = True
        return jsonify({"error": search_results["error"]})
    
    if not search_results:
        session["messages"].append({"role": "bot", "content": "⚠️ No search results found. Try a different query.", "time": datetime.now().strftime("%H:%M")})
        session.modified = True
        return jsonify({"error": "No results"})
    
    session["messages"].append({"role": "bot", "content": "🔍 Searching Google...", "time": datetime.now().strftime("%H:%M"), "typing": True})
    
    report = generate_report(user_message, search_results)
    
    if "Error:" in report:
        session["messages"].append({"role": "bot", "content": f"⚠️ LLM Error: {report}", "time": datetime.now().strftime("%H:%M")})
    else:
        session["messages"].append({"role": "bot", "content": report, "time": datetime.now().strftime("%H:%M")})
    
    session.modified = True
    
    return jsonify({"response": report, "sources": search_results})

@app.route("/clear", methods=["POST"])
def clear():
    session["messages"] = []
    return jsonify({"status": "cleared"})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))