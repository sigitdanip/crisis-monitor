#!/usr/bin/env python3
"""Test LLM connectivity directly"""
import sys, os, time
sys.path.insert(0, '/root/crisis-monitor/backend/src')
os.chdir('/root/crisis-monitor/backend')

from dotenv import load_dotenv
load_dotenv(override=True)

from langchain_openai import ChatOpenAI

api_key = os.environ.get("OPENCODE_GO_API_KEY", "")
print(f"API key present: {bool(api_key)} (len={len(api_key)})")

llm = ChatOpenAI(
    model="deepseek-v4-pro",
    base_url="https://opencode.ai/zen/go/v1",
    api_key=api_key,
    temperature=0.3,
    timeout=25,
)

print("Calling LLM (timeout=25s)...")
start = time.time()
try:
    resp = llm.invoke("Say hello in one word.")
    elapsed = time.time() - start
    print(f"Response ({elapsed:.1f}s): {resp.content[:100]}")
except Exception as e:
    elapsed = time.time() - start
    print(f"FAILED after {elapsed:.1f}s: {type(e).__name__}: {e}")
