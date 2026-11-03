def test_tracking_page_renders_successfully(client):
    response = client.get("/tracking")
    
    assert response.status_code == 200
    assert b"Shipment Tracking" in response.data
    assert b"Enter your tracking number" in response.data
    assert b"Route Map" not in response.data

def test_tracking_with_nonexistent_number(client):
    response = client.get("/tracking?q=CF-NOT-EXIST")
    assert response.status_code == 200
    assert b"No shipment found" in response.data
    assert b"Route Map" not in response.data