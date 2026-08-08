# Plan — Pi Frontier Controls

## 006 — Provider Auth and Budget Fail-Closed

Given a provider call with injected credentials and a fixed budget, when auth is missing, quota is exhausted, timeout occurs, or the provider returns an oversized response, then the call terminates with a typed error, no secret appears in evidence, retries stop at policy, and the authority fingerprint is unchanged.

## 007 — Concurrent Task Backpressure

Given multiple eligible Delta manifests, when workers claim tasks concurrently under global/domain/tool budgets, then stable task keys coalesce duplicates, active attempts stay bounded, fair admission/backpressure is observable, and one task failure does not mutate another task or authority.

## 008 — Session Retention and Privacy Expiry

Given session events, safe summaries, opaque evidence references and crash artifacts, when the retention/expiry policy runs, then raw body and secrets are removed or rejected, audit metadata remains bounded, and expiry cannot delete or alter formal authority data.

## 009 — SDK Upgrade and Requalification

Given an accepted package lock and event/schema registry, when version, integrity, dependency, API or event shape changes, then qualification fails closed, produces a deterministic diff, and feature-flag rollback leaves the legacy path usable.

## Verification

Each experiment records a metadata-only JSON report and updates the corresponding README, the parent Kernel FINDINGS, and the manifest verdict row.
