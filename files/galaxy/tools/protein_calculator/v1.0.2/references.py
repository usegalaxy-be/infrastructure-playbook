# Amino acid data en pK-values
amino_acid_data = {
    "A": {"Long": "Alanine", "Monoisotopic Weight (Da)": 71.03711, "Average Weight (Da)": 71.0788, "dn/dc": 0.167},
    "C": {"Long": "Cysteine", "Monoisotopic Weight (Da)": 103.00919, "Average Weight (Da)": 103.1388,
          "Extinction Coefficient": 125, "dn/dc": 0.206},
    "D": {"Long": "Aspartic acid", "Monoisotopic Weight (Da)": 115.02694, "Average Weight (Da)": 115.0886,
          "dn/dc": 0.197},
    "E": {"Long": "Glutamic acid", "Monoisotopic Weight (Da)": 129.04259, "Average Weight (Da)": 129.1155,
          "dn/dc": 0.183},
    "F": {"Long": "Phenylalanine", "Monoisotopic Weight (Da)": 147.06841, "Average Weight (Da)": 147.1766,
          "dn/dc": 0.244},
    "G": {"Long": "Glycine", "Monoisotopic Weight (Da)": 57.02146, "Average Weight (Da)": 57.0519, "dn/dc": 0.175},
    "H": {"Long": "Histidine", "Monoisotopic Weight (Da)": 137.05891, "Average Weight (Da)": 137.1411, "dn/dc": 0.219},
    "I": {"Long": "Isoleucine", "Monoisotopic Weight (Da)": 113.08406, "Average Weight (Da)": 113.1594, "dn/dc": 0.179},
    "K": {"Long": "Lysine", "Monoisotopic Weight (Da)": 128.09496, "Average Weight (Da)": 128.1741, "dn/dc": 0.181},
    "L": {"Long": "Leucine", "Monoisotopic Weight (Da)": 113.08406, "Average Weight (Da)": 113.1594, "dn/dc": 0.173},
    "M": {"Long": "Methionine", "Monoisotopic Weight (Da)": 131.04049, "Average Weight (Da)": 131.1926, "dn/dc": 0.204},
    "N": {"Long": "Asparagine", "Monoisotopic Weight (Da)": 114.04293, "Average Weight (Da)": 114.1038, "dn/dc": 0.192},
    "O": {"Long": "Pyrrolysine", "Monoisotopic Weight (Da)": 237.147727, "Average Weight (Da)": 237.3018,
          "dn/dc": 0.19},
    "P": {"Long": "Proline", "Monoisotopic Weight (Da)": 97.05276, "Average Weight (Da)": 97.1167, "dn/dc": 0.165},
    "Q": {"Long": "Glutamine", "Monoisotopic Weight (Da)": 128.05858, "Average Weight (Da)": 128.1307, "dn/dc": 0.186},
    "R": {"Long": "Arginine", "Monoisotopic Weight (Da)": 156.10111, "Average Weight (Da)": 156.1875, "dn/dc": 0.206},
    "S": {"Long": "Serine", "Monoisotopic Weight (Da)": 87.03203, "Average Weight (Da)": 87.0782, "dn/dc": 0.170},
    "T": {"Long": "Threonine", "Monoisotopic Weight (Da)": 101.04768, "Average Weight (Da)": 101.1051, "dn/dc": 0.172},
    "U": {"Long": "Selenocysteine", "Monoisotopic Weight (Da)": 150.953636, "Average Weight (Da)": 150.0388,
          "dn/dc": 0.19},
    "V": {"Long": "Valine", "Monoisotopic Weight (Da)": 99.06841, "Average Weight (Da)": 99.1326, "dn/dc": 0.172},
    "W": {"Long": "Tryptophan", "Monoisotopic Weight (Da)": 186.07931, "Average Weight (Da)": 186.2132,
          "Extinction Coefficient": 5500, "dn/dc": 0.277},
    "Y": {"Long": "Tyrosine", "Monoisotopic Weight (Da)": 163.06333, "Average Weight (Da)": 163.1760,
          "Extinction Coefficient": 1490, "dn/dc": 0.240}
}

# Masses were obtained from: https://web.expasy.org/findmod/findmod_masses.html#AA
# dn/dc values were obtained from: https://www.sciencedirect.com/science/article/pii/S0006349511003146
# extinction coeff were obtained from: https://web.expasy.org/protparam/protparam-doc.html
# pK values were obtained from: https://www.vanderbilt.edu/AnS/Chemistry/Rizzo/stuff/AA/AminoAcids.html

#The pI and net_charges are calculated using the Bio.SeqUtils.IsoelectricPoint module (https://biopython.org/docs/1.76/api/Bio.SeqUtils.IsoelectricPoint.html)
#* Bjellqvist, B.,Hughes, G.J., Pasquali, Ch., Paquet, N., Ravier, F.,
#Sanchez, J.-Ch., Frutiger, S. & Hochstrasser, D.F.
#The focusing positions of polypeptides in immobilized pH gradients can be
#predicted from their amino acid sequences. Electrophoresis 1993, 14,
#1023-1031.

#* Bjellqvist, B., Basse, B., Olsen, E. and Celis, J.E.
#Reference points for comparisons of two-dimensional maps of proteins from
#different human cell types defined in a pH scale where isoelectric points
#correlate with polypeptide compositions. Electrophoresis 1994, 15, 529-539.

pK_values = {
    'A': {'COOH': 2.35, 'NH2': 9.87, 'sidechain': None},
    'R': {'COOH': 1.82, 'NH2': 8.99, 'sidechain': 12.48},
    'N': {'COOH': 2.14, 'NH2': 8.72, 'sidechain': None},
    'D': {'COOH': 1.99, 'NH2': 9.90, 'sidechain': 3.90},
    'C': {'COOH': 1.92, 'NH2': 10.70, 'sidechain': 8.37},
    'E': {'COOH': 2.10, 'NH2': 9.47, 'sidechain': 4.07},
    'Q': {'COOH': 2.17, 'NH2': 9.13, 'sidechain': None},
    'G': {'COOH': 2.35, 'NH2': 9.78, 'sidechain': None},
    'H': {'COOH': 1.80, 'NH2': 9.33, 'sidechain': 6.04},
    'I': {'COOH': 2.32, 'NH2': 9.76, 'sidechain': None},
    'L': {'COOH': 2.33, 'NH2': 9.74, 'sidechain': None},
    'K': {'COOH': 2.16, 'NH2': 9.06, 'sidechain': 10.54},
    'M': {'COOH': 2.13, 'NH2': 9.28, 'sidechain': None},
    'F': {'COOH': 2.20, 'NH2': 9.31, 'sidechain': None},
    'P': {'COOH': 1.95, 'NH2': 10.64, 'sidechain': None},
    'S': {'COOH': 2.19, 'NH2': 9.21, 'sidechain': None},
    'T': {'COOH': 2.09, 'NH2': 9.10, 'sidechain': None},
    'W': {'COOH': 2.46, 'NH2': 9.41, 'sidechain': None},
    'Y': {'COOH': 2.20, 'NH2': 9.21, 'sidechain': 10.46},
    'V': {'COOH': 2.29, 'NH2': 9.74, 'sidechain': None}
}

charges = {
    'positive': {'K': 1, 'R': 1, 'H': 0.1},
    'negative': {'D': -1, 'E': -1, 'C': -1, 'Y': -1},
    'Nterm': 1,
    'Cterm': -1
}
