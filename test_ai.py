import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

response = client.responses.create(
    model="gpt-5-mini",
    input="Say hello in one short sentence."
)

print(response.output_text)
