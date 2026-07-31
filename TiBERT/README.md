# TiBERT
## Introduction
To promote the development of Tibetan natural language processing tasks, we collects the large-scale training data from Tibetan websites and constructs a vocabulary that can cover 99.95% of the words in the corpus by using Sentencepiece. Then, we train the Tibetan monolingual pre-trained language model named TiBERT on the data and vocabulary. Finally, we apply TiBERT to the downstream tasks of text classification and question generation, and compare it with classic models and multilingual pre-trained models, the experimental results show that TiBERT can achieve the best performance.

## Contributions
(1) To better express the semantic information of Tibetan and reduce the problem of OOV, We uses the unigram language model of Sentencepiece to segment Tibetan words and constructs a vocabulary that can cover 99.95% of the words in the corpus.  
(2) To further promote the development of various downstream tasks of Tibetan natural language processing, We collected a large-scale Tibetan dataset and trained the monolingual Tibetan pre-trained language model named TiBERT.  
(3) To evaluate the performance of TiBERT, We conducts comparative experiments on the two downstream tasks of text classification and question generation. The experimental results show that the TiBERT is effective.

## Experimental Result
We conduct text classification experiments on the Tibetan News Classification Corpus (TNCC：https://github.com/FudanNLP/Tibetan-Classification) which released by the Natural Language Processing Laboratory of Fudan University for text classification.  
#### Performances on title classification 
![Performances on title classification](https://github.com/user-attachments/assets/05661c27-bade-46f3-b3f5-544d5d45ac99)
#### Performances on document classification  
![Performances on document classification](https://github.com/user-attachments/assets/683479ee-a17a-4ab7-ac5c-65c80acffbce)

## Download

TiBERT Model: https://huggingface.co/CMLI-NLP/TiBERT

TiBERT Paper: https://ieeexplore.ieee.org/document/9945074

## Citation

Plain Text:  
S. Liu, J. Deng, Y. Sun and X. Zhao, "TiBERT: Tibetan Pre-trained Language Model," 2022 IEEE International Conference on Systems, Man, and Cybernetics (SMC), Prague, Czech Republic, 2022, pp. 2956-2961, doi: 10.1109/SMC53654.2022.9945074.

BibTeX:
```
@INPROCEEDINGS{9945074,
  author={Liu, Sisi and Deng, Junjie and Sun, Yuan and Zhao, Xiaobing},
  booktitle={2022 IEEE International Conference on Systems, Man, and Cybernetics (SMC)}, 
  title={TiBERT: Tibetan Pre-trained Language Model}, 
  year={2022},
  volume={},
  number={},
  pages={2956-2961},
  keywords={Vocabulary;Text categorization;Training data;Natural language processing;Data models;Task analysis;Cybernetics;Pre-trained language model;Tibetan;Sentencepiece;TiBERT;Text classification;Question generation},
  doi={10.1109/SMC53654.2022.9945074}}
```

## Disclaimer

This dataset/model is for academic research purposes only. Prohibited for any commercial or unethical purposes.