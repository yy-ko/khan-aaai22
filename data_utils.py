import torch, logging, sys
from torch.utils.data import dataset, DataLoader, random_split, WeightedRandomSampler
from torch.utils.data.distributed import DistributedSampler

# from torchtext.datasets import AG_NEWS
from torchtext.data.utils import get_tokenizer
from torchtext.vocab import build_vocab_from_iterator
from torchtext.data.functional import to_map_style_dataset

from collections import Counter, OrderedDict
from typing import Iterable
import pandas as pd
import numpy as np
import random
from sklearn.model_selection import train_test_split
from sklearn.model_selection import KFold, StratifiedKFold
import nlpaug.augmenter.sentence as nas
import nlpaug.augmenter.word as naw

import main

MAX_WORDS = 80

def yield_tokens(data_iter, tokenizer):
    for _, title, text in data_iter:
        yield tokenizer(title)
        yield tokenizer(str(text))

def preprocess_text(text):
    text = text.str.lower() # lowercase
    text = text.str.replace(r"\#","") # replaces hashtags
    text = text.str.replace(r"http\S+","")  # remove URL addresses
    #  text = text.str.replace(r"@","")
    #  text = text.str.replace(r"[^A-Za-z0-9()!?\'\`\"]", " ")
    #  text = text.str.replace("\s{2,}", " ")
    return text

def augment_text(df_train, df_title, df_label, samples=300, pr=0.2):
    aug_w2v = naw.WordEmbsAug(
    # model_type='word2vec', model_path='../input/nlpword2vecembeddingspretrained/GoogleNews-vectors-negative300.bin',
    model_type='glove', model_path='/home/yyko/workspace/political_pre/glove/glove.6B.300d.txt',
    action="substitute")
    aug_w2v.aug_p=pr
    aug_text=[]
    title = df_title['title'].values.tolist()
    label = df_label['label'].values.tolist()
    ##selecting the minority class samples
    df_n=df_train[df_train.label==1].reset_index(drop=True)

    ## data augmentation loop
    for i in np.random.randint(0,len(df_n),samples):
        text = df_n.iloc[i]['text']
        augmented_text = aug_w2v.augment(text)
        aug_text.append(augmented_text)
    
    ## dataframe
    aug = pd.DataFrame({'title': title, 'text':aug_text, 'label':label})
    df_train=random.shuffle(df_train.append(aug).reset_index(drop=True))
    return df_train

def KFold_data_preprocessing(dataset_n, data_path):
    """
        Args:
            dataset:
            data_path:
        Returns:
            vocab_size:
            num_class:
    """

    num_class = 0

    if dataset_n =='SEMEVAL':
        num_class = 2
        k_folds = 10
        tokenizer = get_tokenizer('basic_english')
        # data_path += '/semeval_sep.csv'
        data_path += '/semeval-new.csv'

    elif dataset_n =='han':
        num_class = 2
        k_folds = 100
        tokenizer = get_tokenizer('basic_english')
        data_path += '/han/han_all_sep.csv'

    elif dataset_n =='ALLSIDES-S':
        num_class = 3
        k_folds = 5
        data_path += '/kcd_allsides_SEP.csv'

    elif dataset_n =='ALLSIDES-L':
        num_class = 5
        k_folds = 10
        data_path += '/khan_split/khan_dataset_01.csv'

    else:
        logging.error('Invalid dataset name!')
        sys.exit(1)

    # read a dataset file from a local path and pre-process it
    dataset = pd.read_csv(data_path)
    
    augment = pd.read_csv('./data/semeval-aug.csv')
    # dataset.dropna(inplace=True)
    # dataset.reset_index(drop=True, inplace=True)
    
    # For K-fold cross validation test
    # dataset = dataset.iloc[:100,]
    
    #  dataset["text"] = preprocess_text(dataset["text"].astype(str))
    # dataset = dataset[['text','title','label']]
    dataset_x = dataset[['text','title']]
    dataset_y = dataset[['label']]

    # augment_x = augment[['text','title']]
    # augment_y = augment[['label']]

    # split a dataset into train/test datasets
    # train_df, test_df = train_test_split(dataset, train_size=0.9)
    
    knowledge_indices = {}
    rep_entity_list = []
    demo_entity_list = []
    common_entity_list = []

    with open('./kgraphs/pre-trained-plus/entities_con.dict') as rep_file:
        while (line := rep_file.readline().rstrip()):
            rep_entity_list.append(line.split()[1])

    with open('./kgraphs/pre-trained-plus/entities_lib.dict') as demo_file:
        while (line := demo_file.readline().rstrip()):
            demo_entity_list.append(line.split()[1])

    with open('./kgraphs/pre-trained/entities_yago.dict') as rep_file:
        while (line := rep_file.readline().rstrip()):
            common_entity_list.append(line.split()[1].split('_')[0].lower())

    #  with open('./kgraphs/pre-trained/entities_FB15K.dict') as rep_file:
        #  while (line := rep_file.readline().rstrip()):
            #  common_entity_list.append(line.split()[1])

    
    Skfold = StratifiedKFold(n_splits=k_folds, shuffle=True, random_state=10)
    # Skfold = StratifiedKFold(n_splits=k_folds, shuffle=False)
    fold_idx = 0
    total_accuracy = 0
    best_accuracy = 0
    total_train_time = 0
    acc_list = []
    # index_list = []
    
    # K-th iteration
    # Extraction each fold train/testset and train
    for train_index, test_index in Skfold.split(dataset_x, dataset_y):
        # index_list.append([train_index, test_index])
        # continue
        fold_idx += 1
        # train_df, test_df = dataset.loc[train_index], dataset.loc[test_index]
        x_train_df, x_test_df = dataset_x.loc[train_index], dataset_x.loc[test_index]
        y_train_df, y_test_df = dataset_y.loc[train_index], dataset_y.loc[test_index]

        # x_train_aug_df = augment_text(x_train_df)
        
        # logging for data statistics
        print('  - Training data size: {}'.format(len(y_train_df)))
        # print('  - Validataion data size: {}'.format(len(val_dataset)))
        print('  - Test data size: {}'.format(len(y_test_df)))
        
        
        # train text augmentation
        '''
        df_title = x_train_df[['title']]
        df_text = x_train_df[['text']]
        df_label = y_train_df[['label']]
        title = df_title['title'].values.tolist()
        label = df_label['label'].values.tolist()
        # print(title)
        # print(label)
        # device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        
        aug_sentence = []
        aug_sen = nas.AbstSummAug(model_path='t5-base', max_length=40000)
        for sen in df_text.text.values.tolist():
            aug_sentence.append(aug_sen.augment(sen, num_thread=8)[0])
        
        # print(len((df_text.text.values.tolist())))
        # print(max([len(i) for i in df_text.text.values.tolist()]))

        # df_text = df_text.iloc[:300,]

        # aug_sentence = aug_sen.augment(df_text.text.values.tolist(), num_thread=8)
        augment = pd.DataFrame({'title' : title, 'text' : aug_sentence, 'label' : label})
        '''
        augment_x = augment[['text','title']]
        augment_y = augment[['label']]
        augment_x.loc[train_index]
        augment_y.loc[train_index]
        
        x_train_aug_df = pd.concat([x_train_df,augment_x])
        y_train_aug_df = pd.concat([y_train_df,augment_y])
        x_train_aug_df.reset_index(drop=True, inplace=True)
        y_train_aug_df.reset_index(drop=True, inplace=True)
        x_train = x_train_aug_df.values
        y_train = y_train_aug_df.values
        x_test = x_test_df.values
        y_test = y_test_df.values
        
        # Weighted Random Sampler
        #class 0 : 366개, class 1 : 214개
        class_counts = y_train_aug_df.value_counts().to_list() # [366, 214]
        # print(class_counts)
        num_samples = sum(class_counts) # 580: 전체 trainset 수
        # print(num_samples)
        labels = y_train_aug_df.values
        # print(labels)
        
        # class 별 가중치 부여 [580/366, 580/214] => class 1에 가중치 높게 부여하게 됨
        class_weights = [num_samples / class_counts[i] for i in range(len(class_counts))] 
        print(class_weights)

        # label에 해당되는 가중치 부여
        weights = [class_weights[labels[i][0]] for i in range(int(num_samples))] #해당 레이블마다의 가중치 비율 setting
        sampler = WeightedRandomSampler(torch.DoubleTensor(weights), int(num_samples))

                                    #      label        title           text
        # train_iter = list(map(lambda x: (x.tolist()[2], x.tolist()[1], x.tolist()[0]), v_train))
        # test_iter = list(map(lambda x: (x.tolist()[2], x.tolist()[1], x.tolist()[0]), v_test))
        train_iter = list(map(lambda x, y: (y.tolist()[0], x.tolist()[1], x.tolist()[0]), x_train, y_train ))
        test_iter = list(map(lambda x, y: (y.tolist()[0], x.tolist()[1], x.tolist()[0]), x_test, y_test ))

        # build vocab
        tokenizer = get_tokenizer('basic_english')
        #  vocab = build_vocab_from_iterator(yield_tokens(train_iter, tokenizer), specials=['<unk>', '<splt>'])
        vocab = build_vocab_from_iterator(yield_tokens(train_iter, tokenizer), specials=['<unk>', '<sep>'])
        vocab.set_default_index(vocab['<unk>'])
        
        rep_lookup_indices = vocab.lookup_indices(rep_entity_list)
        demo_lookup_indices = vocab.lookup_indices(demo_entity_list)
        common_lookup_indices = vocab.lookup_indices(common_entity_list)

        knowledge_indices['rep'] = rep_lookup_indices
        knowledge_indices['demo'] = demo_lookup_indices
        knowledge_indices['common'] = common_lookup_indices

        #  print (len(rep_lookup_indices))
        #  print (len(demo_lookup_indices))
        #  print (len(common_lookup_indices))

        #  print (len(set(rep_lookup_indices)))
        #  print (len(set(demo_lookup_indices)))
        #  print (len(set(common_lookup_indices)))
        
        # train each k-fold 
        fold_accuracy, fold_train_time = main.train_each_fold(train_iter, test_iter, vocab, num_class, knowledge_indices, fold_idx, k_folds, sampler)
        total_accuracy += fold_accuracy
        if fold_accuracy > best_accuracy:
            best_accuracy = fold_accuracy
        
        total_train_time += fold_train_time
        acc_list.append(fold_accuracy)
        # if dataset_n == 'han':
        #     break
        # if dataset_n == 'SEMEVAL':
        #     break
    # index_list_df = pd.DataFrame(index_list, columns=['index','list'])
    # index_list_df.to_csv("/home/yyko/workspace/political_pre/github/khan/index_listttttttttttttttttttttttttt.csv", index=False, encoding='utf-8-sig')
    print('')
    print('=============================== {:2d}-Folds Training Result ==============================='.format(fold_idx))
    print('=============== Total Accuracy: {:.4f},    Training time: {:.2f} (sec.)   ================'.format(total_accuracy/fold_idx, total_train_time))
    print('=============== Best Accuracy: {:.4f},     Accuracy variance: {:.4f}      ================'.format(best_accuracy, np.var(acc_list)))
    print('========================================================================================')
    print('Accuracy_list: ', acc_list)



def get_dataloaders(train_iter, test_iter, vocab, batch_size, max_sentence, sampler, device):
    """
        Args:
        Returns:
            vocab_size:
            num_class:
    """
    tokenizer = get_tokenizer('basic_english')

    train_dataset = to_map_style_dataset(train_iter)
    test_dataset = to_map_style_dataset(test_iter)

    # train_size = int(len(train_dataset) * 1)
    # val_size = len(train_dataset) - train_size
    # train_dataset, val_dataset = random_split(train_dataset, [train_size, val_size])

    def collate_batch(batch): # split a label and text in each row
        title_pipeline = lambda x: vocab(tokenizer(str(x)))
        text_pipeline = lambda x: vocab(tokenizer(x))
        label_pipeline = lambda x: int(x)

        label_list, title_list, sentence_list = [], [], []
        for (_label, _title, _text) in batch:
            label_list.append(label_pipeline(_label))
            title_indices = title_pipeline(_title)
            text_indices = text_pipeline(_text)

            # pad/trucate each article embedding according to maximum article length
            text_size = len(text_indices)

            s_list = []
            sentence_tmp = [] 

            for w_idx in text_indices:
                if w_idx == 1: # end of sentence
                    s_list.append(sentence_tmp)
                    sentence_tmp = []
                else:
                    sentence_tmp.append(w_idx)

            sentence_count = 0
            preprocess_sentence_list = []

            for i, sentence in enumerate(s_list):
                if i >= max_sentence:
                    break
                if len(sentence) < MAX_WORDS:
                    for _ in range(MAX_WORDS - len(sentence)):
                        sentence.append(vocab['<unk>'])
                elif len(sentence) > MAX_WORDS:
                    sentence = sentence[:MAX_WORDS]
                else:
                    pass
                preprocess_sentence_list.append(sentence)

            if len(preprocess_sentence_list) < max_sentence:
                for _ in range(max_sentence - len(preprocess_sentence_list)):
                    preprocess_sentence_list.append([0]*MAX_WORDS)

            sentence_list.append(preprocess_sentence_list)


            title_len = len(title_indices)
            if title_len < MAX_WORDS:
                for _ in range(MAX_WORDS - title_len):
                    title_indices.append(vocab['<unk>'])
            elif title_len > MAX_WORDS:
                title_indices = title_indices[:MAX_WORDS]
            else:
                pass

            title_list.append(title_indices)


        label_list = torch.tensor(label_list, dtype=torch.int64)
        title_list = torch.tensor(title_list, dtype=torch.int64)
        sentence_list = torch.tensor(sentence_list, dtype=torch.int64)
        return label_list.to(device), title_list.to(device), sentence_list.to(device)

    # sampler addition
    train_dataloader = DataLoader(train_dataset, batch_size=batch_size, shuffle=False, sampler = sampler, collate_fn=collate_batch)
    # train_dataloader = DataLoader(train_dataset, batch_size=batch_size, shuffle=False, collate_fn=collate_batch)
    valid_dataloader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, collate_fn=collate_batch)
    test_dataloader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, collate_fn=collate_batch)

    return train_dataloader, valid_dataloader, test_dataloader
