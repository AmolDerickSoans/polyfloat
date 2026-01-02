import pytest
import asyncio
import json
from datetime import datetime
from pathlib import Path
from polycli.emergency import EmergencyStopController, StopReason
from polycli.emergency.controller import EmergencyStopError


@pytest.fixture
def temp_stop_file(tmp_path, monkeypatch):
    """Use temporary directory for stop file."""
    stop_file = tmp_path / ".emergency_stop"
    monkeypatch.setattr(EmergencyStopController, "STOP_FILE", stop_file)
    yield
    if stop_file.exists():
        stop_file.unlink()


@pytest.mark.asyncio
async def test_trigger_stop(temp_stop_file):
    """Test triggering emergency stop."""
    controller = EmergencyStopController()
    
    assert not controller.is_stopped
    
    event = await controller.trigger_stop(
        reason=StopReason.USER_INITIATED,
        description="Test stop"
    )
    
    assert controller.is_stopped
    assert event.reason == StopReason.USER_INITIATED
    assert controller.STOP_FILE.exists()
    assert event.orders_cancelled == 0
    assert event.websockets_closed == 0


@pytest.mark.asyncio
async def test_resume(temp_stop_file):
    """Test resuming from emergency stop."""
    controller = EmergencyStopController()
    
    await controller.trigger_stop()
    assert controller.is_stopped
    
    result = await controller.resume(resumed_by="test")
    assert result is True
    assert not controller.is_stopped
    assert not controller.STOP_FILE.exists()
    assert controller.current_event.resumed_by == "test"
    assert controller.current_event.resumed_at is not None


@pytest.mark.asyncio
async def test_stop_persists_across_instances(temp_stop_file):
    """Test that stop state persists across controller instances."""
    controller1 = EmergencyStopController()
    event1 = await controller1.trigger_stop(
        reason=StopReason.USER_INITIATED,
        description="Test persistence"
    )
    
    controller2 = EmergencyStopController()
    assert controller2.is_stopped
    assert controller2.current_event.id == event1.id
    assert controller2.current_event.description == "Test persistence"


@pytest.mark.asyncio
async def test_check_and_raise(temp_stop_file):
    """Test check_and_raise raises error when stopped."""
    controller = EmergencyStopController()
    
    await controller.trigger_stop(description="Emergency test")
    
    with pytest.raises(EmergencyStopError) as exc_info:
        controller.check_and_raise()
    
    assert "Emergency stop active" in str(exc_info.value)
    assert "Emergency test" in str(exc_info.value)
    
    await controller.resume()
    
    controller.check_and_raise()


@pytest.mark.asyncio
async def test_stop_callbacks_called(temp_stop_file):
    """Test that both sync and async stop callbacks are called."""
    controller = EmergencyStopController()
    
    stop_callback_called = False
    async_stop_callback_called = False
    received_event = None
    
    def stop_callback(event):
        nonlocal stop_callback_called, received_event
        stop_callback_called = True
        received_event = event
    
    async def async_stop_callback(event):
        nonlocal async_stop_callback_called
        async_stop_callback_called = True
    
    controller.register_stop_callback(stop_callback)
    controller.register_stop_callback(async_stop_callback)
    
    event = await controller.trigger_stop(
        reason=StopReason.USER_INITIATED,
        description="Test callbacks"
    )
    
    assert stop_callback_called
    assert async_stop_callback_called
    assert received_event.id == event.id


@pytest.mark.asyncio
async def test_resume_callbacks_called(temp_stop_file):
    """Test that both sync and async resume callbacks are called."""
    controller = EmergencyStopController()
    
    resume_callback_called = False
    async_resume_callback_called = False
    
    def resume_callback():
        nonlocal resume_callback_called
        resume_callback_called = True
    
    async def async_resume_callback():
        nonlocal async_resume_callback_called
        async_resume_callback_called = True
    
    controller.register_resume_callback(resume_callback)
    controller.register_resume_callback(async_resume_callback)
    
    await controller.trigger_stop()
    
    result = await controller.resume(resumed_by="test")
    
    assert result is True
    assert resume_callback_called
    assert async_resume_callback_called


@pytest.mark.asyncio
async def test_stop_state_file_format(temp_stop_file):
    """Test the format of the stop state file."""
    controller = EmergencyStopController()
    
    await controller.trigger_stop(
        reason=StopReason.USER_INITIATED,
        description="Test file format"
    )
    
    with open(controller.STOP_FILE) as f:
        data = json.load(f)
    
    assert "id" in data
    assert "timestamp" in data
    assert "reason" in data
    assert "description" in data
    assert "triggered_by" in data
    
    assert data["reason"] == "user_initiated"
    assert data["description"] == "Test file format"
    assert data["triggered_by"] == "user"
    
    import datetime
    timestamp = datetime.datetime.fromisoformat(data["timestamp"])
    assert isinstance(timestamp, datetime.datetime)
