# CredentialVerdict

CredentialVerdict dies without GenLayer: no EVM contract can read a Credly badge page and cross-reference an AWS verification portal on-chain to confirm whether a credential is genuine — only GenLayer's AI validators can fetch live credential pages during consensus and produce a tamper-proof multi-node verified attestation.

## Problem

In the remote-work and AI-agent economy, anyone can claim certifications they do not hold: "Certified Solidity Auditor", "AWS Solutions Architect", "CFA Level 3". Existing credential checks are centralized (trust one company), slow (days to weeks), and not composable on-chain. There is no neutral, tamper-proof way to verify a credential before hiring an agent or granting access.

## Solution

CredentialVerdict stores a credential claim, fetches the public credential page (and an optional issuer verification portal) during consensus, and asks GenLayer validators to cross-check the holder, credential name, and issuing organization. The verdict is written on-chain permanently. Later lookups reuse the URL cache so the same page is not re-verified from scratch.

Remove `web.render` and the LLM and this contract is only a registry of whatever the submitter typed. The on-chain read is the product.

## How it works

1. **Submit.** Anyone calls `submit_claim` with the holder name, credential name, issuing organization, credential URL, and an optional issuer verification URL. The claim is stored as `PENDING`, and `url_cache[credential_url]` points at the new claim id.
2. **Verify.** Anyone calls `verify_claim`. Validators fetch both URLs on-chain and run the credential checklist.
3. **Read the verdict.** `get_verdict` returns the ruling, confidence, reasoning, and issues. `get_claim` returns the full record.
4. **Lookup cache.** `lookup_by_url` returns the stored claim for a credential URL, or `{"found": false}` when that URL has never been submitted.

## Verdict types

| Verdict | Meaning |
| --- | --- |
| `VERIFIED` | Key details match and the credential appears genuine and active. |
| `INVALID` | The page was readable, but the claim does not match (wrong name, wrong issuer, revoked, expired, or clearly fake). |
| `UNVERIFIABLE` | The page could not be read (login wall, 404, fetch failure) or there is not enough information to decide. `PENDING` claims have not been evaluated yet. |

Confidence is an integer from 0 to 100. `issues_found` is empty when the verdict is `VERIFIED`.

## Consensus design

`verify_claim` runs inside `gl.vm.run_nondet_unsafe`.

- The leader fetches each URL inside its own try/except, so a failed page becomes text in the prompt instead of aborting the call.
- The leader always returns a dict. Malformed model output becomes `UNVERIFIABLE` with confidence 0. An unknown verdict string is normalized to `UNVERIFIABLE`.
- Validators accept the leader only when the verdict matches **exactly**. `VERIFIED` versus `INVALID` is a binary credential decision, so there is no numeric tolerance on the verdict itself.
- Confidence uses the same three bands as the approved reference contracts: 0-34, 35-79, and 80-100. Validators must land in the same band. Reasoning text is not compared.

## Use cases

- AI agent hiring: check a claimed certification before assigning work.
- DAO membership: gate a role on a public credential page.
- DeFi KYC-lite: attest that a public certification page matches a claimed identity, without a centralized vendor.
- Job boards: show a stored verdict next to an applicant instead of trusting a self-reported badge.

## Supported credential sources

Any public verification URL, including:

- Credly badge pages
- LinkedIn certification pages that are publicly readable
- Coursera completion pages
- University transcript or verification pages
- Issuer portals such as an AWS certificate verification URL

The second URL is optional. Pass `""` to verify from the primary page only.

## Edge cases handled

- Login walls, 404s, and pages that are too short to read become `UNVERIFIABLE` instead of crashing.
- Revoked or expired credentials are `INVALID` when the page says so.
- Holder-name and issuing-organization mismatches are `INVALID`.
- A fetch exception on one or both URLs is caught per URL. The call still completes.
- Malformed model JSON falls back to `UNVERIFIABLE` with confidence 0.
- The same credential URL is cached on submit so `lookup_by_url` can find the claim without scanning every record.
- Only the contract owner can invalidate a `PENDING` claim. Already evaluated claims stay as they are.

## Deploy on GenLayer Studio (studionet)

1. Open [GenLayer Studio](https://studio.genlayer.com) and create an Intelligent Contract.
2. Paste `contracts/credential_verdict.py`. The file header must stay the first lines (v0.2.16 and the `py-genlayer` dependency). Do not add a frontend.
3. Select network **studionet**.
4. Deploy. The constructor takes no arguments and sets `owner` to the deployer.
5. Call `submit_claim(holder_name, credential_name, issuing_org, credential_url, issuer_verify_url)`.
6. Call `verify_claim(claim_id)`. Then read `get_verdict(claim_id)` or `lookup_by_url(credential_url)`.

## Run tests

```bash
pip install -r requirements-dev.txt
pytest tests/test_credential_verdict.py -v
```

## Contract address

Deployed on GenLayer Studio (studionet):

`0x42e1e4385bf4d8e8220EF8c187371934eCc320A5`

Explorer: https://explorer-studio.genlayer.com/address/0x42e1e4385bf4d8e8220EF8c187371934eCc320A5
