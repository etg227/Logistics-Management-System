def test_404_page_renders_custom_template(client):
    response = client.get("/this-page-does-not-exist-12345")
    
    assert response.status_code == 404
    assert b"Unable to complete your request" in response.data
    assert b"404" in response.data

def test_403_page_renders_custom_template(client):
    client.post("/login", data={"email": "driver@example.com", "password": "test-password-123"})
    
    response = client.get("/admin/users/")
    
    assert response.status_code == 403
    assert b"Unable to complete your request" in response.data
    assert b"403" in response.data
    assert b"permission" in response.data