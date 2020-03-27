import pyspark
from pyspark.context import SparkContext
from pyspark.sql.session import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import *

import tensorflow as tf
import tensorflow_hub as thub
import bert

import pandas as pd
import numpy as np

import re

import random

import os
from tqdm import tqdm

def init_bert(bert_version="https://tfhub.dev/tensorflow/bert_en_wwm_cased_L-24_H-1024_A-16/1", trainable=True, do_lower_case=False):

	"""
	Load params and vocab from existing BERT model

	Returns: bert_layer object and bert_tokenizer
	"""

	bert_layer = thub.KerasLayer(bert_version,trainable=trainable)
	vocabulary_file = bert_layer.resolved_object.vocab_file.asset_path.numpy()
	BertTokenizer = bert.bert_tokenization.FullTokenizer
	tokenizer = BertTokenizer(vocabulary_file, do_lower_case=do_lower_case)

	return bert_layer, tokenizer


def init_spark(dynamic_allocation="True", executor_cores="2"):

	"""
	Initialize Spark context

	Returns: Spark session object
	"""

	config = pyspark.SparkConf().setAll([("spark.dynamicAllocation.enabled",dynamic_allocation),
                                    ("spark.executor.cores",executor_cores)])
	sc = SparkContext(conf=config)
	spark = SparkSession(sc)

	return sc, spark

def load_data(spark_context, bucket_name, dataset):
    
    """
    Takes in the name of csv file in GCS and the name of the GCS bucket
    and loads it in as a Spark dataframe

    Returns: Spark df of only sarcastic, Spark df of only non-sacrastic, and the ratio 
    between the two of them 
    """
    
    sarc = spark_context.read.csv("gs://{}/{}.csv".format(bucket_name, dataset), 
                          inferSchema=True, header=False, sep = ',')
    sarc = sarc.withColumnRenamed('_c0','label').withColumnRenamed('_c1','subreddit').withColumnRenamed('_c2','context')
    sarcastic = sarc.where(F.col('label')==1)
    non_sarcastic = sarc.where(F.col('label')==0)
    sarc_cnt = sarcastic.count()
    non_sarc_cnt = non_sarcastic.count()
    ratio = sarc_cnt / non_sarc_cnt
    
    # dropping subreddit column before returning
    sarcastic = sarcastic.drop('subreddit')
    non_sarcastic = non_sarcastic.drop('subreddit')
    
    return sarcastic, non_sarcastic, ratio


def pad(epoch_df, pad_by_batch=False):

    """
    Takes in a Spark dataframe
    Returns: A list of token, label tuples ordered
    by token sequence length
    """
    
    # add sequence lengths
    epoch_df = epoch_df.withColumn("sequence_length", F.size(epoch_df.tokens))
        
    # order by sequence length
    epoch_df = epoch_df.orderBy("sequence_length", ascending=False)
            
    # drop sequence length column
    epoch_df = epoch_df.drop("sequence_length")
            
    # convert to pandas
    epoch_df = epoch_df.toPandas()

    # convert to list of tuples
    dflist = [(epoch_df['tokens'].iloc[i], epoch_df['labels'].iloc[i]) for i in range(len(epoch_df))]

    if pad_by_batch==False:

        # convert to tf dataset via tf generator
        processed_dataset = tf.data.Dataset.from_generator(lambda: dflist, output_types=(tf.int32, tf.int32))

        # call the generator where 'batch' size is just the length of the whole dataset. 
        batched_dataset = processed_dataset.padded_batch(len(epoch_df), padded_shapes=((None,),()))

        return batched_dataset

    elif pad_by_batch==True:

        # convert to tf dataset via tf generator
        processed_dataset = tf.data.Dataset.from_generator(lambda: dflist, output_types=(tf.int32, tf.int32))

        # call the generator where batch size is pre-determined
        batched_dataset = processed_dataset.padded_batch(5, padded_shapes=((),(None,)))

        return batched_dataset



def pad_by_overall_length2(epoch_df):
    
    """
    Takes in a Spark dataframe 
    Returns: nparray padded by the longest sequence in the entire
    dataset
    """
    
    # Start with three empty lists and initialize var for max_seq_len
    tokens, X, y = [], [], []
    max_seq_len = 0
    
    # convert pandas
    epoch_df = epoch_df.toPandas()
    
    # generator for iterating over df
    for _, row in tqdm(epoch_df.iterrows()):
        
        # pull out raw tokens and label for each row
        raw_tokens, label = epoch_df.iloc[_]['tokens'], epoch_df.iloc[_]['label']
        
        # update max sequence length var
        max_seq_len = max(max_seq_len, len(raw_tokens))
      
        # append results as list to empty list
        tokens.append(raw_tokens)
        y.append(label)
    
    # convert response to nparray
    y = np.array(y)

    # for each of the raw tokens
    for sample in tokens:
        
        # truncate sample list if for some reason max_seq_len is shorter than actual length 
        sample = sample[:min(len(sample), max_seq_len - 2)]
        
        # add zeros to pad the elements if length of sample is less then max_seq_len
        sample = sample + [0] * (max_seq_len - len(sample))
        
        # append result to empty list X
        X.append(np.array(sample))
    
    # convert predictor to nparray
    X = np.array(X)
    
    return X,y
        
def sort_by_comment_length(epoch_df, batch_size=16):
    
    """
    Takes in a Spark dataframe
    Returns: A list of token, label tuples ordered
    by token sequence length
    """
    
    # add sequence lengths
    epoch_df = epoch_df.withColumn("sequence_length", F.size(epoch_df.tokens))
        
    # order by sequence length
    epoch_df = epoch_df.orderBy("sequence_length", ascending=False)
            
    # drop sequence length column
    epoch_df = epoch_df.drop("sequence_length")
            
    # convert pandas
    epoch_df = epoch_df.toPandas()
    
    # convert to sorted list of tuples
    sorted_tokens = [(epoch_df['tokens'].iloc[i], epoch_df['label'].iloc[i]) for i in range(len(epoch_df))]
    
    return sorted_tokens
            



        
                
    







