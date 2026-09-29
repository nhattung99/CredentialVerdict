import json
import pytest


def test_verified_with_both_urls(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")

    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Nguyen Van A",
            "AWS Solutions Architect - Associate",
            "Amazon Web Services",
            "https://credly.com/badges/abc123",
            "https://aws.amazon.com/verification/abc123",
        )
    assert claim_id == "1"
    assert contract.get_count() == 1

    direct_vm.mock_web(
        r".*credly.*",
        "Nguyen Van A earned AWS Solutions Architect - Associate "
        "issued by Amazon Web Services on 2025-06-15",
    )
    direct_vm.mock_web(
        r".*aws.*verification.*",
        "Certificate ID abc123: Nguyen Van A - AWS Solutions Architect Associate - ACTIVE",
    )

    direct_vm.mock_llm(
        r".*credential verification.*",
        json.dumps({
            "verdict": "VERIFIED",
            "confidence": 96,
            "reasoning": "Credly badge and AWS portal both confirm the credential for Nguyen Van A.",
            "issues_found": "",
        }),
    )

    contract.verify_claim(claim_id)

    result = json.loads(contract.get_verdict(claim_id))
    assert result["verdict"] == "VERIFIED"
    assert result["confidence"] == 96
    assert result["issues_found"] == ""

    full = json.loads(contract.get_claim(claim_id))
    assert full["status"] == "VERIFIED"


def test_verified_primary_url_only(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")

    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Nguyen Van A",
            "AWS Solutions Architect - Associate",
            "Amazon Web Services",
            "https://credly.com/badges/primary-only",
            "",
        )
    assert claim_id == "1"

    direct_vm.mock_web(
        r".*credly.*",
        "Nguyen Van A earned AWS Solutions Architect - Associate issued by Amazon Web Services. Status: ACTIVE.",
    )
    direct_vm.mock_llm(
        r".*credential verification.*",
        json.dumps({
            "verdict": "VERIFIED",
            "confidence": 88,
            "reasoning": "The primary credential page confirms the holder, credential, and issuer.",
            "issues_found": "",
        }),
    )

    contract.verify_claim(claim_id)

    result = json.loads(contract.get_verdict(claim_id))
    assert result["verdict"] == "VERIFIED"
    assert result["confidence"] == 88
    full = json.loads(contract.get_claim(claim_id))
    assert full["status"] == "VERIFIED"
    assert full["issuer_verify_url"] == ""


def test_invalid_name_mismatch(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")

    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Nguyen Van A",
            "AWS Solutions Architect - Associate",
            "Amazon Web Services",
            "https://credly.com/badges/name-mismatch",
            "",
        )

    direct_vm.mock_web(
        r".*credly.*",
        "Tran Thi B earned AWS Solutions Architect - Associate issued by Amazon Web Services.",
    )
    direct_vm.mock_llm(
        r".*credential verification.*",
        json.dumps({
            "verdict": "INVALID",
            "confidence": 93,
            "reasoning": "The badge page names a different holder than the claim.",
            "issues_found": "Name on page does not match",
        }),
    )

    contract.verify_claim(claim_id)

    result = json.loads(contract.get_verdict(claim_id))
    assert result["verdict"] == "INVALID"
    assert result["issues_found"] == "Name on page does not match"
    full = json.loads(contract.get_claim(claim_id))
    assert full["status"] == "INVALID"


def test_invalid_wrong_issuer(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")

    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Nguyen Van A",
            "AWS Solutions Architect - Associate",
            "Amazon Web Services",
            "https://credly.com/badges/wrong-issuer",
            "",
        )

    direct_vm.mock_web(
        r".*credly.*",
        "Nguyen Van A earned AWS Solutions Architect - Associate issued by Google Cloud.",
    )
    direct_vm.mock_llm(
        r".*credential verification.*",
        json.dumps({
            "verdict": "INVALID",
            "confidence": 91,
            "reasoning": "The page lists Google Cloud, not Amazon Web Services.",
            "issues_found": "Issuing organization does not match",
        }),
    )

    contract.verify_claim(claim_id)

    result = json.loads(contract.get_verdict(claim_id))
    assert result["verdict"] == "INVALID"
    full = json.loads(contract.get_claim(claim_id))
    assert full["status"] == "INVALID"


def test_invalid_revoked_credential(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")

    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Nguyen Van A",
            "AWS Solutions Architect - Associate",
            "Amazon Web Services",
            "https://credly.com/badges/revoked",
            "https://aws.amazon.com/verification/revoked",
        )

    direct_vm.mock_web(
        r".*credly.*",
        "Nguyen Van A - AWS Solutions Architect - Associate - status REVOKED by Amazon Web Services.",
    )
    direct_vm.mock_web(
        r".*aws.*verification.*",
        "Certificate status: REVOKED. This credential is no longer active.",
    )
    direct_vm.mock_llm(
        r".*credential verification.*",
        json.dumps({
            "verdict": "INVALID",
            "confidence": 97,
            "reasoning": "Both pages show the credential was revoked.",
            "issues_found": "Credential is revoked",
        }),
    )

    contract.verify_claim(claim_id)

    result = json.loads(contract.get_verdict(claim_id))
    assert result["verdict"] == "INVALID"
    assert "revok" in result["issues_found"].lower()
    full = json.loads(contract.get_claim(claim_id))
    assert full["status"] == "INVALID"


def test_unverifiable_page_not_readable(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")

    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Nguyen Van A",
            "AWS Solutions Architect - Associate",
            "Amazon Web Services",
            "https://credly.com/badges/login-wall",
            "",
        )

    direct_vm.mock_web(r".*credly.*", "404")
    direct_vm.mock_llm(
        r".*credential verification.*",
        json.dumps({
            "verdict": "UNVERIFIABLE",
            "confidence": 20,
            "reasoning": "The credential page was empty or too short to read.",
            "issues_found": "Page not readable",
        }),
    )

    contract.verify_claim(claim_id)

    result = json.loads(contract.get_verdict(claim_id))
    assert result["verdict"] == "UNVERIFIABLE"
    full = json.loads(contract.get_claim(claim_id))
    assert full["status"] == "UNVERIFIABLE"


def test_unverifiable_both_urls_fail(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")

    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Nguyen Van A",
            "AWS Solutions Architect - Associate",
            "Amazon Web Services",
            "https://credly.com/badges/both-fail",
            "https://aws.amazon.com/verification/both-fail",
        )

    def _raise(_url=None):
        raise RuntimeError("source unreachable")

    direct_vm.mock_web(r".*credly.*", _raise)
    direct_vm.mock_web(r".*aws.*", _raise)
    direct_vm.mock_llm(
        r".*credential verification.*",
        json.dumps({
            "verdict": "UNVERIFIABLE",
            "confidence": 5,
            "reasoning": "Both the credential page and the issuer portal failed to load.",
            "issues_found": "Fetch failed for both URLs",
        }),
    )

    contract.verify_claim(claim_id)

    full = json.loads(contract.get_claim(claim_id))
    assert full["status"] == "UNVERIFIABLE"
    result = json.loads(contract.get_verdict(claim_id))
    assert result["verdict"] == "UNVERIFIABLE"


def test_malformed_llm_json_fallback(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")

    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Nguyen Van A",
            "AWS Solutions Architect - Associate",
            "Amazon Web Services",
            "https://credly.com/badges/bad-json",
            "",
        )

    direct_vm.mock_web(
        r".*credly.*",
        "Nguyen Van A earned AWS Solutions Architect - Associate issued by Amazon Web Services.",
    )
    direct_vm.mock_llm(r".*credential verification.*", "not valid json at all!!")

    contract.verify_claim(claim_id)

    result = json.loads(contract.get_verdict(claim_id))
    assert result["verdict"] == "UNVERIFIABLE"
    assert result["confidence"] == 0
    full = json.loads(contract.get_claim(claim_id))
    assert full["status"] == "UNVERIFIABLE"


def test_invalid_verdict_normalized(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")

    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Nguyen Van A",
            "AWS Solutions Architect - Associate",
            "Amazon Web Services",
            "https://credly.com/badges/maybe",
            "",
        )

    direct_vm.mock_web(
        r".*credly.*",
        "Nguyen Van A earned AWS Solutions Architect - Associate issued by Amazon Web Services.",
    )
    direct_vm.mock_llm(
        r".*credential verification.*",
        json.dumps({
            "verdict": "MAYBE",
            "confidence": 55,
            "reasoning": "The model was unsure.",
            "issues_found": "Unrecognized verdict",
        }),
    )

    contract.verify_claim(claim_id)

    result = json.loads(contract.get_verdict(claim_id))
    assert result["verdict"] == "UNVERIFIABLE"
    full = json.loads(contract.get_claim(claim_id))
    assert full["status"] == "UNVERIFIABLE"


def test_empty_holder_name_rejected(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("holder_name cannot be empty"):
            contract.submit_claim(
                "",
                "AWS SAA",
                "AWS",
                "https://credly.com/abc",
                "",
            )


def test_empty_credential_name_rejected(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("credential_name cannot be empty"):
            contract.submit_claim(
                "Name",
                "",
                "AWS",
                "https://credly.com/abc",
                "",
            )


def test_invalid_credential_url(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("Invalid credential_url"):
            contract.submit_claim("Name", "Cert", "Org", "not-a-url", "")


def test_invalid_issuer_url(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("Invalid issuer_verify_url"):
            contract.submit_claim(
                "Name",
                "Cert",
                "Org",
                "https://credly.com/abc",
                "bad-url",
            )


def test_verify_already_verified(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")

    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Nguyen Van A",
            "AWS Solutions Architect - Associate",
            "Amazon Web Services",
            "https://credly.com/badges/already",
            "",
        )

    direct_vm.mock_web(
        r".*credly.*",
        "Nguyen Van A earned AWS Solutions Architect - Associate issued by Amazon Web Services.",
    )
    direct_vm.mock_llm(
        r".*credential verification.*",
        json.dumps({
            "verdict": "VERIFIED",
            "confidence": 90,
            "reasoning": "Details match the credential page.",
            "issues_found": "",
        }),
    )

    contract.verify_claim(claim_id)
    assert json.loads(contract.get_verdict(claim_id))["verdict"] == "VERIFIED"

    with direct_vm.expect_revert("not PENDING"):
        contract.verify_claim(claim_id)


def test_get_verdict_pending(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")
    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Name",
            "Cert",
            "Org",
            "https://credly.com/abc",
            "",
        )
    with direct_vm.expect_revert("Not yet evaluated"):
        contract.get_verdict(claim_id)


def test_lookup_by_url_found(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")
    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Name",
            "Cert",
            "Org",
            "https://credly.com/abc",
            "",
        )
    result = json.loads(contract.lookup_by_url("https://credly.com/abc"))
    assert result["found"] != False or result.get("claim_id") == claim_id
    assert result.get("claim_id") == claim_id
    assert result["holder_name"] == "Name"
    assert result["status"] == "PENDING"


def test_lookup_by_url_not_found(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")
    result = json.loads(contract.lookup_by_url("https://nonexistent.com/xyz"))
    assert result.get("found") == False


def test_list_claims_filter(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/credential_verdict.py")

    with direct_vm.prank(direct_alice):
        verified_id = contract.submit_claim(
            "Alice Holder",
            "AWS Solutions Architect - Associate",
            "Amazon Web Services",
            "https://credly.com/badges/alice",
            "",
        )
    with direct_vm.prank(direct_bob):
        pending_id = contract.submit_claim(
            "Bob Holder",
            "CFA Level 3",
            "CFA Institute",
            "https://credly.com/badges/bob",
            "",
        )

    direct_vm.mock_web(
        r".*alice.*",
        "Alice Holder earned AWS Solutions Architect - Associate issued by Amazon Web Services.",
    )
    direct_vm.mock_llm(
        r".*credential verification.*",
        json.dumps({
            "verdict": "VERIFIED",
            "confidence": 94,
            "reasoning": "The badge page matches Alice Holder and Amazon Web Services.",
            "issues_found": "",
        }),
    )
    contract.verify_claim(verified_id)

    pending = json.loads(contract.list_claims("PENDING"))
    verified = json.loads(contract.list_claims("VERIFIED"))
    all_claims = json.loads(contract.list_claims(""))

    assert len(pending) == 1
    assert pending[0]["claim_id"] == pending_id
    assert pending[0]["status"] == "PENDING"

    assert len(verified) == 1
    assert verified[0]["claim_id"] == verified_id
    assert verified[0]["verdict"] == "VERIFIED"

    assert len(all_claims) == 2


def test_invalidate_owner_only(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/credential_verdict.py")

    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Nguyen Van A",
            "AWS Solutions Architect - Associate",
            "Amazon Web Services",
            "https://credly.com/badges/admin",
            "",
        )

    with direct_vm.prank(direct_bob):
        with direct_vm.expect_revert("Only owner"):
            contract.invalidate_claim(claim_id)

    contract.invalidate_claim(claim_id)
    full = json.loads(contract.get_claim(claim_id))
    assert full["status"] == "UNVERIFIABLE"
    assert full["reasoning"] == "Invalidated by admin"


def test_invalidate_non_pending(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/credential_verdict.py")

    with direct_vm.prank(direct_alice):
        claim_id = contract.submit_claim(
            "Nguyen Van A",
            "AWS Solutions Architect - Associate",
            "Amazon Web Services",
            "https://credly.com/badges/locked",
            "",
        )

    direct_vm.mock_web(
        r".*credly.*",
        "Nguyen Van A earned AWS Solutions Architect - Associate issued by Amazon Web Services.",
    )
    direct_vm.mock_llm(
        r".*credential verification.*",
        json.dumps({
            "verdict": "VERIFIED",
            "confidence": 92,
            "reasoning": "The credential page matches the claim.",
            "issues_found": "",
        }),
    )
    contract.verify_claim(claim_id)

    with direct_vm.expect_revert("only PENDING claims"):
        contract.invalidate_claim(claim_id)
