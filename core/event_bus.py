"""
404Bot v2 - Event Bus
Provides event-driven communication between bot components
"""

import asyncio
import logging
from typing import Dict, List, Callable, Any

class EventBus:
    """
    Event bus for asynchronous communication between components
    Implements a publish-subscribe pattern for decoupled architecture
    """
    
    def __init__(self):
        """Initialize the event bus"""
        self.subscribers = {}
        self.logger = logging.getLogger("EventBus")
    
    def subscribe(self, event_type: str, callback: Callable):
        """
        Subscribe to an event type
        
        Args:
            event_type: Type of event to subscribe to
            callback: Function to call when event is published
        """
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        
        if callback not in self.subscribers[event_type]:
            self.subscribers[event_type].append(callback)
            self.logger.debug(f"Subscribed to event: {event_type}")
    
    def unsubscribe(self, event_type: str, callback: Callable):
        """
        Unsubscribe from an event type
        
        Args:
            event_type: Type of event to unsubscribe from
            callback: Function to remove from subscribers
        """
        if event_type in self.subscribers and callback in self.subscribers[event_type]:
            self.subscribers[event_type].remove(callback)
            self.logger.debug(f"Unsubscribed from event: {event_type}")
    
    def publish(self, event_type: str, data: Any = None):
        """
        Publish an event synchronously
        
        Args:
            event_type: Type of event to publish
            data: Data to pass to subscribers
        """
        if event_type not in self.subscribers:
            return
        
        for callback in self.subscribers[event_type]:
            try:
                callback(data)
            except Exception as e:
                self.logger.error(f"Error in event handler for {event_type}: {str(e)}")
    
    async def publish_async(self, event_type: str, data: Any = None):
        """
        Publish an event asynchronously
        
        Args:
            event_type: Type of event to publish
            data: Data to pass to subscribers
        """
        if event_type not in self.subscribers:
            return
        
        tasks = []
        for callback in self.subscribers[event_type]:
            if asyncio.iscoroutinefunction(callback):
                tasks.append(asyncio.create_task(callback(data)))
            else:
                try:
                    callback(data)
                except Exception as e:
                    self.logger.error(f"Error in event handler for {event_type}: {str(e)}")
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    def clear_subscribers(self, event_type: str = None):
        """
        Clear subscribers for a specific event type or all events
        
        Args:
            event_type: Type of event to clear subscribers for, or None for all
        """
        if event_type:
            if event_type in self.subscribers:
                self.subscribers[event_type] = []
                self.logger.debug(f"Cleared subscribers for event: {event_type}")
        else:
            self.subscribers = {}
            self.logger.debug("Cleared all subscribers")
