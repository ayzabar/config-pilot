# AI-Assisted Configuration Manager: Implementation Report

**Author:** Bahri Ayzabar
**Role:** DevOps Engineer Intern Candidate
**Date:** February 2026

---

Building a reliable configuration manager with a local LLM is a unique engineering challenge. This document outlines how I tamed the unpredictability of local AI, the architectural choices I made, and why I treated the LLM as a tool rather than a wizard.

## 1. The Brain: Llama 3.1 (Local)

I selected **Llama 3.1** running via Ollama as the inference engine.

- **Why?** It currently offers the best performance-to-resource ratio for open-weights models.
- **The Challenge:** Local models have a significantly limited context window compared to cloud giants like GPT-4. If you feed them a massive JSON file, they tend to hallucinate keys or lose track of the structure. Recognizing this limitation was central to my engineering strategy.

## 2. The Strategy: "Scope Isolation"

Initially, I attempted a naive approach: sending the entire application configuration to the LLM for modification.
**Result:** It failed significantly. The model flattened nested structures, omitted required fields, and struggled with the file size.

To solve this, I pivoted to a **Scope Isolation** strategy (what I call "The Surgeon Method").

Instead of asking the AI to rewrite the entire file, I programmed the system to only expose the relevant parts.

1.  **Extract:** The Python backend programmatically extracts _only_ the relevant `workload` snippet (e.g., just the containers and replicas).
2.  **Prompt:** I feed this focused, isolated context to the LLM.
3.  **Merge:** The LLM returns a clean update, and I use Python to surgically graft it back into the original JSON tree.

**Trade-off:** I sacrificed the ability for the AI to edit arbitrary root-level fields freely, but I gained **100% reliability**. I believe stability is more valuable than unchecked creative freedom in configuration management.

---

## 3. Architecture & Flow

I designed the system as a modular, containerized microservices architecture.

- **`bot-server`**: Handles user input and manages the AI interaction.
- **`schema-server`**: Serves the JSON Schemas to ensure type safety.
- **`values-server`**: Serves the current configuration values.

### The Request Lifecycle

1.  **User:** Sends a natural language request (e.g., "set tournament memory to 2Gi").
2.  **Identification:** The Bot asks the AI to identify the target application.
3.  **Fetch:** The Bot retrieves the full JSON configuration and the Schema.
4.  **Isolation (The Surgery):** Python logic extracts just the `workload` section.
5.  **Inference:** The AI updates that specific section.
6.  **Reconstruction:** The Bot stitches the update back into the main JSON, sanitizes the output (removing Markdown artifacts), and validates it against the schema.
7.  **Response:** The user receives a valid, updated JSON.

_Note: Following the project guidelines (if an LLM is used to implement the svc, use the `_jk` suffix in one of the func name) , I added the `_jk` suffix to one function in each main.py file._
_AI was used as a helper during development, think of it as a senior giving guidance rather than writing the code._

---

## 4. Challenges & Solutions

### The "Router" Ambiguity (Strict Persona Pattern)

**Problem:** The local LLM occasionally struggled to classify user intent correctly. It would often produce conversational output (e.g., "The application is tournament") or fail to map generic terms like "game" to the correct service (`matchmaking`).

**Solution:** Instead of writing complex if-else chains, I solved this via **Strict Persona Prompting**.

1.  **Persona Adoption:** I instructed the LLM to act exclusively as a "Strict API Router," providing it with a explicit keyword map (e.g., mapping "cup", "bracket" -> `tournament`).
2.  **Negative Constraints:** I used strong negative constraints in the system prompt (e.g., "Do NOT output punctuation," "Do NOT write full sentences") to force a deterministic, single-word output.
3.  **Safety Net:** As a final layer of defense, if the model breaks character and outputs text, a Python-based sanitizer strips the noise and searches for the valid service keywords within the raw response.

This approach proves that with the right prompting strategy, even small local models can handle logic routing reliably.

### The "Flattening" Issue

**Problem:** The AI had a tendency to take deep structures like `workloads -> statefulsets -> containers` and move them to the root level.
**Solution:** I stopped relying on the AI for structural integrity. I let Python handle the hierarchy and used the AI strictly for value updates.

### Markdown Pollution

**Problem:** The model often wrapped outputs in Markdown code blocks or added conversational filler.
**Solution:** I built a regex-based cleaning pipeline to strip away everything except the raw JSON data before processing.

---

## 5. Conclusion

This project demonstrates that you don't need massive cloud resources to build intelligent tools. By combining **probabilistic AI** (for understanding intent) with **deterministic code** (for structural manipulation), I built a system that is robust, efficient, and reliable.
