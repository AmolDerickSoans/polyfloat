

@app.websocket("/ws/news")
async def websocket_news_endpoint(websocket: WebSocket, user_id: str = Query(..., description="User identifier")):
    """WebSocket endpoint for real-time news updates"""
    connection_manager = app_state.get("connection_manager")
    if not connection_manager:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER, reason="Service not ready")
        return

    await websocket.accept()

    connected = await connection_manager.connect(user_id, websocket)
    if not connected:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User already connected")
        return

    logger.info(f"WebSocket connection established for user: {user_id}")

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                logger.debug(f"Received message from user {user_id}", message=message)

                if message.get("type") == "ping":
                    await connection_manager.send_to_user(
                        user_id,
                        {"type": "pong", "timestamp": time.time()}
                    )
                elif message.get("type") == "subscribe":
                    logger.info(f"User {user_id} updated filters", filters=message.get("filters"))

            except json.JSONDecodeError:
                logger.warning(f"Received invalid JSON from user {user_id}")
                await connection_manager.send_to_user(
                    user_id,
                    {"type": "error", "message": "Invalid JSON"}
                )
            except Exception as e:
                logger.error(f"Error processing message from user {user_id}", error=str(e))
                await connection_manager.send_to_user(
                    user_id,
                    {"type": "error", "message": "Internal server error"}
                )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user: {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}", exc_info=True)
    finally:
        await connection_manager.disconnect(user_id)
        logger.info(f"Cleaned up connection for user: {user_id}")


@app.websocket("/ws/news")
async def websocket_news_endpoint(websocket: WebSocket, user_id: str = Query(..., description="User identifier")):
    """WebSocket endpoint for real-time news updates"""
    connection_manager = app_state.get("connection_manager")
    if not connection_manager:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER, reason="Service not ready")
        return

    await websocket.accept()

    connected = await connection_manager.connect(user_id, websocket)
    if not connected:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User already connected")
        return

    logger.info(f"WebSocket connection established for user: {user_id}")

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                logger.debug(f"Received message from user {user_id}", message=message)

                if message.get("type") == "ping":
                    await connection_manager.send_to_user(
                        user_id,
                        {"type": "pong", "timestamp": time.time()}
                    )
                elif message.get("type") == "subscribe":
                    logger.info(f"User {user_id} updated filters", filters=message.get("filters"))

            except json.JSONDecodeError:
                logger.warning(f"Received invalid JSON from user {user_id}")
                await connection_manager.send_to_user(
                    user_id,
                    {"type": "error", "message": "Invalid JSON"}
                )
            except Exception as e:
                logger.error(f"Error processing message from user {user_id}", error=str(e))
                await connection_manager.send_to_user(
                    user_id,
                    {"type": "error", "message": "Internal server error"}
                )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user: {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}", exc_info=True)
    finally:
        await connection_manager.disconnect(user_id)
        logger.info(f"Cleaned up connection for user: {user_id}")
