"""Token counting utilities with fallback handling."""

import tiktoken
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def get_encoding_for_model(model_name: str):
    """
    Get tiktoken encoding for a model with fallback to cl100k_base.
    
    Args:
        model_name: The name of the model
        
    Returns:
        tiktoken.Encoding: The encoding for the model
    """
    try:
        encoding = tiktoken.encoding_for_model(model_name)
        logger.debug(f"Successfully loaded encoding for model: {model_name}")
        return encoding
    except KeyError:
        logger.warning(f"Model {model_name} not found in tiktoken. Using cl100k_base encoding as fallback.")
        encoding = tiktoken.get_encoding("cl100k_base")
        return encoding


def count_tokens_safe(messages: List[Dict[str, Any]], model_name: str = "gpt-4o-mini") -> int:
    """
    Count tokens in messages with safe fallback handling.
    
    Args:
        messages: List of message dictionaries
        model_name: Name of the model to use for encoding
        
    Returns:
        int: Number of tokens
    """
    try:
        encoding = get_encoding_for_model(model_name)
        
        # Convert messages to text for token counting
        text_content = ""
        for message in messages:
            if isinstance(message, dict):
                content = message.get('content', '')
                role = message.get('role', '')
                text_content += f"{role}: {content}\n"
            else:
                text_content += str(message) + "\n"
        
        token_count = len(encoding.encode(text_content))
        logger.debug(f"Token count for {len(messages)} messages: {token_count}")
        return token_count
        
    except Exception as e:
        logger.error(f"Error counting tokens: {e}")
        # Fallback: rough estimation (4 characters per token)
        total_chars = sum(len(str(msg)) for msg in messages)
        estimated_tokens = total_chars // 4
        logger.warning(f"Using character-based estimation: {estimated_tokens} tokens")
        return estimated_tokens


def safe_encode_text(text: str, model_name: str = "gpt-4o-mini") -> List[int]:
    """
    Safely encode text with fallback handling.
    
    Args:
        text: Text to encode
        model_name: Model name for encoding
        
    Returns:
        List[int]: Token IDs
    """
    try:
        encoding = get_encoding_for_model(model_name)
        return encoding.encode(text)
    except Exception as e:
        logger.error(f"Error encoding text: {e}")
        # Fallback to empty list
        return []


def safe_decode_tokens(tokens: List[int], model_name: str = "gpt-4o-mini") -> str:
    """
    Safely decode tokens with fallback handling.
    
    Args:
        tokens: List of token IDs
        model_name: Model name for decoding
        
    Returns:
        str: Decoded text
    """
    try:
        encoding = get_encoding_for_model(model_name)
        return encoding.decode(tokens)
    except Exception as e:
        logger.error(f"Error decoding tokens: {e}")
        # Fallback to empty string
        return ""
