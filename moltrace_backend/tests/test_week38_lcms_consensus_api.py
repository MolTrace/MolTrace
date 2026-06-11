def test_lcms_feature_family_consensus_endpoint(client):
    with client:
        client.post("/auth/register", json={"email": "consensus@example.com", "password": "StrongPassword123!"})
        login = client.post("/auth/login", json={"email": "consensus@example.com", "password": "StrongPassword123!"})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        payload = {
            "feature_table_text": "group_id,representative_mz,aligned_rt_min,label,sample_area,blank_area,blank_ratio,blank_subtracted_area,member_count,roles_present\nG001,301.200000,5.000000,sample_enriched_feature,1000,0,0,1000,1,sample\nG002,302.203355,5.010000,sample_enriched_feature,220,0,0,220,1,sample\n",
            "formula": "C20H30O",
            "min_consensus_score_to_promote": 0.3,
        }
        res = client.post("/ms/lcms/features/consensus", headers=headers, json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["family_count"] >= 1
        assert data["relationship_count"] >= 1
        assert data["family_table_text"].startswith("family_id")
