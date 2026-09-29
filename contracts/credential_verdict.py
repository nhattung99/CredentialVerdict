# v0.2.16
# {
#   "Seq": [
#     { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
#   ]
# }
import json
from dataclasses import dataclass
from genlayer import *


def _addr_str(a: Address) -> str:
    try:
        return a.as_hex
    except Exception:
        return str(a)


def _to_address(val) -> Address:
    if isinstance(val, Address):
        return val
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str.startswith("0x"):
            val_str = "0x" + val_str
        return Address(val_str)
    return Address(val)


def _is_http_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


@allow_storage
@dataclass
class CredentialClaim:
    submitter: Address
    holder_name: str
    credential_name: str
    issuing_org: str
    credential_url: str
    issuer_verify_url: str
    status: str
    verdict: str
    confidence: u256
    reasoning: str
    issues_found: str


class CredentialVerdict(gl.Contract):
    claims: TreeMap[str, CredentialClaim]
    next_id: bigint
    owner: Address
    url_cache: TreeMap[str, str]

    def __init__(self):
        self.owner = _to_address(gl.message.sender_address)
        self.next_id = bigint(1)

    def _claim_dict(self, claim_id: str, claim: CredentialClaim) -> dict:
        return {
            "claim_id": claim_id,
            "submitter": _addr_str(claim.submitter),
            "holder_name": claim.holder_name,
            "credential_name": claim.credential_name,
            "issuing_org": claim.issuing_org,
            "credential_url": claim.credential_url,
            "issuer_verify_url": claim.issuer_verify_url,
            "status": claim.status,
            "verdict": claim.verdict,
            "confidence": int(claim.confidence),
            "reasoning": claim.reasoning,
            "issues_found": claim.issues_found,
        }

    @gl.public.write
    def submit_claim(
        self,
        holder_name: str,
        credential_name: str,
        issuing_org: str,
        credential_url: str,
        issuer_verify_url: str,
    ) -> str:
        if not holder_name or len(holder_name.strip()) == 0:
            raise gl.vm.UserError("holder_name cannot be empty")
        if len(holder_name) > 100:
            raise gl.vm.UserError("holder_name cannot exceed 100 characters")

        if not credential_name or len(credential_name.strip()) == 0:
            raise gl.vm.UserError("credential_name cannot be empty")
        if len(credential_name) > 150:
            raise gl.vm.UserError("credential_name cannot exceed 150 characters")

        if not issuing_org or len(issuing_org.strip()) == 0:
            raise gl.vm.UserError("issuing_org cannot be empty")
        if len(issuing_org) > 100:
            raise gl.vm.UserError("issuing_org cannot exceed 100 characters")

        if not credential_url or not _is_http_url(credential_url):
            raise gl.vm.UserError("Invalid credential_url")

        if issuer_verify_url != "":
            if not _is_http_url(issuer_verify_url):
                raise gl.vm.UserError("Invalid issuer_verify_url")

        claim_id = str(self.next_id)
        self.next_id += bigint(1)

        claim = CredentialClaim(
            submitter=_to_address(gl.message.sender_address),
            holder_name=holder_name,
            credential_name=credential_name,
            issuing_org=issuing_org,
            credential_url=credential_url,
            issuer_verify_url=issuer_verify_url,
            status="PENDING",
            verdict="PENDING",
            confidence=u256(0),
            reasoning="",
            issues_found="",
        )
        self.claims[claim_id] = claim
        self.url_cache[credential_url] = claim_id
        return claim_id

    @gl.public.write
    def verify_claim(self, claim_id: str) -> None:
        if claim_id not in self.claims:
            raise gl.vm.UserError("Claim not found")

        claim = self.claims[claim_id]
        if claim.status != "PENDING":
            raise gl.vm.UserError("Claim is not PENDING")

        credential_url_cap = claim.credential_url
        issuer_verify_url_cap = claim.issuer_verify_url
        holder_name_cap = claim.holder_name
        credential_name_cap = claim.credential_name
        issuing_org_cap = claim.issuing_org

        def leader_fn():
            try:
                credential_page = ""
                try:
                    res = gl.nondet.web.render(credential_url_cap)
                    body = res.body if hasattr(res, "body") else str(res)
                    credential_page = (
                        body[:4000]
                        if body and len(body.strip()) > 30
                        else "(empty or too short)"
                    )
                except Exception as e:
                    credential_page = f"(fetch failed: {str(e)})"

                issuer_page = ""
                if issuer_verify_url_cap:
                    try:
                        res2 = gl.nondet.web.render(issuer_verify_url_cap)
                        body2 = res2.body if hasattr(res2, "body") else str(res2)
                        issuer_page = (
                            body2[:3000]
                            if body2 and len(body2.strip()) > 30
                            else "(empty or too short)"
                        )
                    except Exception as e:
                        issuer_page = f"(fetch failed: {str(e)})"
                else:
                    issuer_page = "(no issuer verification URL provided)"

                prompt = f"""You are an expert credential verification specialist on GenLayer.
Your job is to verify whether a claimed professional credential is genuine
by reading the credential page and cross-referencing with the issuer portal.

Claimed Credential Details:
- Holder Name: {holder_name_cap}
- Credential Name: {credential_name_cap}
- Issuing Organization: {issuing_org_cap}

Primary Credential Page fetched on-chain:
{credential_page}

Issuer Verification Portal fetched on-chain:
{issuer_page}

Verification checklist:
1. Does the credential page clearly show this specific credential name?
2. Does the holder name on the page match the claimed holder name
   (allow minor formatting differences like middle initials)?
3. Does the issuing organization on the page match the claimed issuer?
4. Is there any indication the credential is expired, revoked, or fake?
5. Is the page a legitimate credential page (not a 404, login wall,
   or unrelated page)?

Verdict options:
- "VERIFIED": All key details match, credential appears genuine and active
- "INVALID": Credential page was readable but details do not match the
  claim (wrong name, wrong issuer, revoked, expired, or clearly fake)
- "UNVERIFIABLE": Page could not be read, returned a login wall/404,
  or does not contain enough information to make a determination

Confidence 0-100: certainty of the verdict.
issues_found: specific mismatches or problems found (empty string if VERIFIED).

Return ONLY raw JSON, no markdown, no backticks:
{{"verdict": "VERIFIED"|"INVALID"|"UNVERIFIABLE",
  "confidence": <0-100>,
  "reasoning": "<2-3 sentences explaining the verdict>",
  "issues_found": "<specific issues or empty string>"}}"""

                raw = gl.nondet.exec_prompt(prompt, response_format="json")

                try:
                    if isinstance(raw, dict):
                        parsed = raw
                    else:
                        cleaned = str(raw).strip()
                        if cleaned.startswith("```json"):
                            cleaned = cleaned[7:]
                        if cleaned.startswith("```"):
                            cleaned = cleaned[3:]
                        if cleaned.endswith("```"):
                            cleaned = cleaned[:-3]
                        parsed = json.loads(cleaned.strip())

                    verdict = parsed.get("verdict", "UNVERIFIABLE")
                    if verdict not in ["VERIFIED", "INVALID", "UNVERIFIABLE"]:
                        verdict = "UNVERIFIABLE"

                    try:
                        conf = max(0, min(100, int(parsed.get("confidence", 0))))
                    except Exception:
                        conf = 0

                    return {
                        "verdict": verdict,
                        "confidence": conf,
                        "reasoning": str(parsed.get("reasoning", "")),
                        "issues_found": str(parsed.get("issues_found", "")),
                    }
                except Exception as e:
                    return {
                        "verdict": "UNVERIFIABLE",
                        "confidence": 0,
                        "reasoning": f"Parse error: {str(e)}",
                        "issues_found": "",
                    }
            except Exception as e:
                return {
                    "verdict": "UNVERIFIABLE",
                    "confidence": 0,
                    "reasoning": f"Parse error: {str(e)}",
                    "issues_found": "",
                }

        def validator_fn(leader_res) -> bool:
            # Exact verdict match: VERIFIED vs INVALID is a binary decision.
            if not isinstance(leader_res, gl.vm.Return):
                return False
            lp = leader_res.calldata
            if not isinstance(lp, dict):
                return False

            leader_verdict = lp.get("verdict")
            leader_conf = lp.get("confidence")

            if leader_verdict not in ["VERIFIED", "INVALID", "UNVERIFIABLE"]:
                return False
            try:
                lc = int(leader_conf)
                if not (0 <= lc <= 100):
                    return False
            except Exception:
                return False

            try:
                my_result = leader_fn()
            except Exception:
                return False

            if my_result.get("verdict") != leader_verdict:
                return False

            try:
                mc = int(my_result.get("confidence", 0))
                if not (0 <= mc <= 100):
                    return False
            except Exception:
                return False

            def _band(c):
                if c < 35:
                    return 1
                elif c < 80:
                    return 2
                else:
                    return 3

            return _band(mc) == _band(lc)

        ruling = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        result_data = ruling.calldata if hasattr(ruling, "calldata") else ruling
        if not isinstance(result_data, dict):
            result_data = {
                "verdict": "UNVERIFIABLE",
                "confidence": 0,
                "reasoning": "Invalid nondet result",
                "issues_found": "",
            }

        result_verdict = result_data.get("verdict", "UNVERIFIABLE")
        if result_verdict not in ["VERIFIED", "INVALID", "UNVERIFIABLE"]:
            result_verdict = "UNVERIFIABLE"

        try:
            result_conf = max(0, min(100, int(result_data.get("confidence", 0))))
        except Exception:
            result_conf = 0

        claim.verdict = result_verdict
        claim.status = result_verdict
        claim.confidence = u256(result_conf)
        claim.reasoning = str(result_data.get("reasoning", ""))
        claim.issues_found = str(result_data.get("issues_found", ""))
        self.claims[claim_id] = claim

    @gl.public.write
    def invalidate_claim(self, claim_id: str) -> None:
        if claim_id not in self.claims:
            raise gl.vm.UserError("Claim not found")

        sender = _to_address(gl.message.sender_address)
        if sender != self.owner:
            raise gl.vm.UserError("Only owner")

        claim = self.claims[claim_id]
        if claim.status != "PENDING":
            raise gl.vm.UserError("only PENDING claims")

        claim.status = "UNVERIFIABLE"
        claim.verdict = "UNVERIFIABLE"
        claim.reasoning = "Invalidated by admin"
        self.claims[claim_id] = claim

    @gl.public.view
    def get_claim(self, claim_id: str) -> str:
        if claim_id not in self.claims:
            raise gl.vm.UserError("Claim not found")
        return json.dumps(self._claim_dict(claim_id, self.claims[claim_id]))

    @gl.public.view
    def get_verdict(self, claim_id: str) -> str:
        if claim_id not in self.claims:
            raise gl.vm.UserError("Claim not found")

        claim = self.claims[claim_id]
        if claim.status == "PENDING":
            raise gl.vm.UserError("Not yet evaluated")

        res = {
            "claim_id": claim_id,
            "holder_name": claim.holder_name,
            "credential_name": claim.credential_name,
            "issuing_org": claim.issuing_org,
            "verdict": claim.verdict,
            "confidence": int(claim.confidence),
            "reasoning": claim.reasoning,
            "issues_found": claim.issues_found,
        }
        return json.dumps(res)

    @gl.public.view
    def lookup_by_url(self, credential_url: str) -> str:
        if credential_url not in self.url_cache:
            return json.dumps({"found": False})

        claim_id = self.url_cache[credential_url]
        if claim_id not in self.claims:
            return json.dumps({"found": False})

        data = self._claim_dict(claim_id, self.claims[claim_id])
        data["found"] = True
        return json.dumps(data)

    @gl.public.view
    def list_claims(self, verdict_filter: str) -> str:
        allowed = ["", "PENDING", "VERIFIED", "INVALID", "UNVERIFIABLE"]
        if verdict_filter not in allowed:
            raise gl.vm.UserError("Invalid verdict filter")

        results = []
        limit = int(self.next_id)
        for i in range(1, limit):
            claim_id = str(i)
            if claim_id in self.claims:
                claim = self.claims[claim_id]
                if verdict_filter == "" or claim.status == verdict_filter:
                    results.append({
                        "claim_id": claim_id,
                        "holder_name": claim.holder_name,
                        "credential_name": claim.credential_name,
                        "issuing_org": claim.issuing_org,
                        "status": claim.status,
                        "verdict": claim.verdict,
                    })
        return json.dumps(results)

    @gl.public.view
    def get_count(self) -> int:
        return int(self.next_id) - 1
