from vertexai import agent_engines
import vertexai

vertexai.init(project="supadha-dev", location="us-central1")
a = agent_engines.get("projects/supadha-dev/locations/us-central1/reasoningEngines/647710755050749952")

print("Testing CSE sub-agent question:")
for event in a.stream_query(user_id="someone@example.com", message="What is binary search tree time complexity?"):
    if 'content' in event and 'parts' in event['content']:
        for part in event['content']['parts']:
            if 'text' in part:
                print(f"[{event.get('author', 'agent')}]: {part['text']}")
