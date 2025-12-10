"""
Utility functions for text processing.
"""
import re
from typing import List


def split_into_sentences(text: str) -> List[str]:
    """
    Split text into sentences for TTS streaming.
    
    Args:
        text: Text to split
        
    Returns:
        List of sentences (with punctuation)
    """
    # Split on sentence endings (. ! ?) followed by whitespace or end of string
    # This regex captures the punctuation with the sentence
    pattern = r'([.!?]+)\s*'
    parts = re.split(pattern, text)
    
    # Recombine sentences with their punctuation
    sentences = []
    i = 0
    while i < len(parts):
        if i + 1 < len(parts) and parts[i + 1].strip():
            # Combine sentence with its punctuation
            sentence = parts[i] + parts[i + 1]
            if sentence.strip():
                sentences.append(sentence.strip())
            i += 2
        else:
            # Last part (may be incomplete sentence)
            if parts[i].strip():
                sentences.append(parts[i].strip())
            i += 1
    
    # Filter out empty sentences
    return [s for s in sentences if s]


def extract_complete_sentences(text: str) -> tuple[List[str], str]:
    """
    Extract complete sentences from text, returning remaining incomplete text.
    
    Args:
        text: Text to process
        
    Returns:
        Tuple of (complete_sentences, remaining_text)
    """
    sentences = split_into_sentences(text)
    
    # Check if last sentence is complete (ends with punctuation)
    if sentences:
        last_sentence = sentences[-1]
        if not re.search(r'[.!?]+$', last_sentence):
            # Last sentence is incomplete
            remaining = sentences.pop()
            return sentences, remaining
    
    return sentences, ""

