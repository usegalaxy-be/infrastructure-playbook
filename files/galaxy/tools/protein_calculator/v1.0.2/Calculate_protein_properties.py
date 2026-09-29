from references import amino_acid_data,charges
from Bio.SeqUtils import IsoelectricPoint
from Bio.Seq import Seq

def calculate_total_masses(amino_acid, count):
    """
    Calculates the total monoisotopic and average masses for the given amino acid and count.

    Args:
        amino_acid (str): The amino acid letter.
        count (int): The number of occurrences of the amino acid in the text.

    Returns:
        tuple: A tuple containing the total monoisotopic mass and the total average mass.
    """
    data = amino_acid_data.get(amino_acid)
    if data:
        total_monoisotopic_mass = data['Monoisotopic Weight (Da)'] * count
        total_average_mass = data['Average Weight (Da)'] * count
        return total_monoisotopic_mass, total_average_mass
    else:
        return 0, 0


def calculate_extinction_coefficient(amino_acid, count, all_cysteines_form_cystines):
    """
    Calculates the extinction coefficient for the given amino acid and count.

    Args:
        amino_acid (str): The amino acid letter.
        count (int): The number of occurrences of the amino acid in the text.
        all_cysteines_form_cystines (bool): If True, all cysteine residues appear as half cystines.

    Returns:
        float: The extinction coefficient.
    """
    data = amino_acid_data.get(amino_acid)
    if data and "Extinction Coefficient" in data:
        if amino_acid == "C":
            if all_cysteines_form_cystines:
                return data["Extinction Coefficient"] * (count // 2)  # Half of the cysteines form cystines
            else:
                return 0  # All cysteines are reduced
        else:
            return data["Extinction Coefficient"] * count
    else:
        return 0

# Function to calculate pI
def get_isoelectric_point(sequence):
    seq = Seq(sequence)
    pI = IsoelectricPoint.IsoelectricPoint(seq).pi()
    return pI

# Function to calculate net charge for different pH
def get_net_charge(sequence):
    seq = Seq(sequence)
    pI = IsoelectricPoint.IsoelectricPoint(seq)

    ph_values = [i / 2 for i in range(4, 25)]
    charges = {ph: pI.charge_at_pH(ph) for ph in ph_values}

    return charges

def calculate_dn_dc(sequence, amino_acid_data):
    """
    Calculates the dn/dc for the given amino acid sequence.

    Args:
        sequence (str): The amino acid sequence.
        amino_acid_data (dict): amino acid information.

    Returns:
        float: The calculated dn/dc value.
    """
    total_dn_dc = 0.0
    for aa in sequence:
        if aa in amino_acid_data:
            total_dn_dc += amino_acid_data[aa].get('dn/dc', 0)  # Fallback to 0 if dn/dc value is not available
    return total_dn_dc / len(sequence)
