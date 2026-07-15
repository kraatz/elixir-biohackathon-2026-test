---
id: TM-001
name: Sensitive Data Access During Pipeline Reasoning
description: >
  While executing the requested pipeline, the agent reads, modifies, or
  deletes private data and may expose it in its output.
assets:
  - user-records
  - credentials
  - internal-documents
stride:
  - information-disclosure
  - tampering
severity: high
related: []
references:
  - "OWASP LLM06: Sensitive Information Disclosure"
  - "OWASP LLM08: Excessive Agency"
last_reviewed: 2026-07-15
---

# TM-001: Sensitive Data Access During Pipeline Reasoning

## Description

While executing the requested pipeline, the agent reads, modifies, or deletes
private data and may expose it in its output. The agent's legitimate reasoning
process becomes the vehicle for unauthorized data access.

## Affected Assets

Sensitive/private data accessible to the agent, e.g. user records,
credentials, and internal documents.

## Security Properties Violated

- **Information Disclosure**: reading and exposing sensitive data in the chat output.
- **Tampering**: modifying or deleting the data during
  pipeline execution.

## Attack Scenarios

1. **Malicious user prompt**: a user directly prompts the agent to access
   sensitive data and return it in the chat.
2. **Indirect prompt injection**: instructions embedded in documents or tool
   outputs processed during the pipeline cause the agent to access or leak
   the data without the user asking directly.

## Preconditions

- The agent has read (and/or write/delete) access to the sensitive data store.
- No output filtering or data-loss-prevention layer exists between the agent
  and the chat response.
- User input is passed to the agent without restriction on data-access
  requests.

## Mitigations

### Preventive

- Do not grant the agent access to sensitive data (least privilege).
- Scope credentials to only what the pipeline requires.

### Detective

- Monitor user prompts and agent outputs using governance/DLP tools.
- Log all data-access operations performed by the agent.

### Responsive

- Revoke agent credentials upon detection of unauthorized access.
- Alert the security team and quarantine the affected session.

