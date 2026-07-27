import vertexai
from vertexai.preview import reasoning_engines

print("Connecting to your deployed Agent Engine...")
vertexai.init(project="supadha-dev", location="us-central1")

# Connect to your specific deployed reasoning engine
remote_agent = reasoning_engines.ReasoningEngine(
    "projects/1019856256943/locations/us-central1/reasoningEngines/2467165004508430336"
)

print("Sending a test message to the cloud...\n")
response = remote_agent.query(input="What can you help me with?")

print("Response from Cloud Agent:")
print("-" * 40)
# Depending on how the agent returns the response, it might be a string or dict
if isinstance(response, dict) and "output" in response:
    print(response["output"])
else:
    print(response)
print("-" * 40)
