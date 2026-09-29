import re


def normalize_sequence(sequence):
    return re.sub(r'\s+', '', sequence)


# Check for validity of protein sequence
def check_protein_sequence(sequence):
    protein_pattern = re.compile("^[ACDEFGHIKLMNOPQRSTUVWY]+$", re.IGNORECASE)
    DNA_pattern = re.compile(r'^[ACTG]+$', re.IGNORECASE)
    seq_length = len(sequence)
    min_seq_length = 10
    max_seq_length = 3000

    # Check if sequence is a valid DNA sequence
    if DNA_pattern.match(sequence):
        error_message = f"Sequence is a DNA sequence. Please enter a valid Protein Sequence."
        return error_message

    # Check if sequence is a valid protein sequence
    for char in sequence:
        if not protein_pattern.match(char):
            error_message = (
                f"Protein sequence contains invalid character: \"{char}\". \n Please enter a valid Protein "
                f"Sequence.")
            return error_message

    # Check if sequence is a valid protein sequence of minimum 10 amino acids
    if seq_length < min_seq_length:
        error_message = (f"Protein sequence should have a minimum length of 10 residues, the input sequence has a "
                         f"length of {seq_length}.")
        return error_message

    # Check if sequence is a valid protein sequence of max 3000 amino acids
    if seq_length > max_seq_length:
        error_message = (f"Protein sequence exceeds the maximum allowed length of {max_seq_length} amino acids. "
                         f"Please shorten the sequence and try again. If longer sequences are required, please contact "
                         f"the tool developer for further assistance.")
        return error_message

    return None


# Format the protein sequence in a nice way in the Results page
def format_sequence(sequence, line_length=55, show_residue_number=False):
    sequence = normalize_sequence(sequence)

    # Insert spaces every 10 residues
    formatted_sequence = ' '.join(sequence[i:i + 10] for i in range(0, len(sequence), 10))

    lines = []
    residue_count = 0  # To track the number of residues processed

    for match in re.finditer(r'(.{1,' + str(line_length) + r'})(?: |$)', formatted_sequence):
        line = match.group(1)
        residue_count += len(re.sub(r' ', '', line))  # Count residues in this line (ignoring spaces)

        if show_residue_number:
            line_rest = line_length - len(line)
            line += (" " * line_rest) + f" {residue_count}"
        lines.append(line)

    return '\n'.join(lines)


def letter_count(text):
    """
    Counts the frequency of each letter in the given text string.

    Args:
      text (str): The text string to be analyzed.

    Returns:
      dict: A dictionary with keys as letters and values as their counts.
    """
    frequency = {}
    for letter in text.upper():
        if letter in frequency:
            frequency[letter] += 1
        else:
            frequency[letter] = 1
    return frequency
