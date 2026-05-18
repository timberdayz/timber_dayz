from pathlib import Path


def test_deploy_workflow_publishes_exact_git_tag_for_backend_and_frontend():
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")

    assert "type=ref,event=tag" in workflow
    assert "type=raw,value=${{ github.ref_name }}-full" in workflow


def test_deploy_workflow_pushes_cnb_using_release_tag():
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")

    assert 'TAG="${GITHUB_REF#refs/tags/}"' in workflow
    assert 'docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME_BACKEND }}:${TAG}' in workflow
    assert 'docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME_FRONTEND }}:${TAG}' in workflow
