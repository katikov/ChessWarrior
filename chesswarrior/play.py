"""ChessWarrior play chess"""

import logging
import os
import matplotlib.pyplot as plt
import time
import multiprocessing
import threading
import numpy as np
import keras
from keras.models import load_model
import chess 

from .model import ChessModel
from .config import Config
from .utils import convert_board_to_plane, get_all_possible_moves, first_person_view_fen, get_feature_plane, \
    is_black_turn, first_person_view_policy


logger = logging.getLogger(__name__)

class MyThread(threading.Thread):
    def __init__(self, func, args=()):
        threading.Thread.__init__(self)
        self.func = func
        self.args = args

    def run(self):
        self.result = self.func(*self.args)

    def get_result(self):
        try:
            return self.result
        except Exception:
            return None




class Player(object):
    """Using the best model to play"""
    def __init__(self, config: Config):
        self.config = config
        self.model_path = self.config.resources.best_model_dir
        self.model = None
        self.value_movel = None
        self.board = None
        self.choise = None
        self.search_depth = 3
        self.move_value = {}
        self.move_hash = {}
        self.policies = []
        self.cnt = []
        self.moves_cnt = 0

        self.INF = 0x3f3f3f3f

    def start(self, choise):
        try:
            self.model = load_model(os.path.join(self.config.resources.best_model_dir, "best_model.h5"))
            self.value_model = load_model(os.path.join(self.config.resources.best_model_dir, "value.h5"))
            logger.info("Load best model successfully.")
        except OSError:
            logger.fatal("Model cannot find!")
            return

        self.board = chess.Board()
        self.choise = choise
        all_moves = get_all_possible_moves()
        self.move_hash = {move: i for (i, move) in enumerate(all_moves)}

        if choise == 1:
            self.board = chess.Board(first_person_view_fen(self.board.fen(), 1))  #???????????????
            print(self.board)
            while True:
                opponent_move = input("your move:")
                try:
                    convert_move = convert_black_uci(opponent_move)
                    convert_move = self.board.parse_uci(convert_move)
                    break
                except ValueError:
                    logger.info("Opponent make a illegal move")
            logger.info("Your move: %s" % opponent_move)
            self.board.push(convert_move) # other move.  update board
        
        while not self.board.is_game_over():
            start = time.time()
            my_move = self.play()   #get ai move
            end = time.time()
            print("time: %.2f" % (end - start))
            #my_move = convert_black_uci(my_move)
            convert_move = self.board.parse_uci(my_move)
            self.board.push(convert_move) # ai move. update board
            if choise == 1:
                logger.info("AI move: %s" % convert_black_uci(my_move))
            else:
                logger.info("AI move: %s" % my_move)
            
            print(self.board)
            while True:
                opponent_move = input("your move:")
                if opponent_move == "undo": #undo 
                    self.board.pop()
                    self.board.pop()
                    logger.info("Undo done.")
                    self.moves_cnt -= 1
                    continue
                try:
                    if choise == 1:
                        convert_move = convert_black_uci(opponent_move)
                    else:
                        convert_move = opponent_move
                    convert_move = self.board.parse_uci(convert_move)
                    break
                except ValueError:
                    logger.info("Opponent make a illegal move")
            logger.info("Your move: %s" % opponent_move)
            
            self.board.push(convert_move) # other move.  update board

    
    def play(self):
        """
        return my move
        ????????????????????????????????????????????????????????????
        ?????????????????????start?????????????????????????????????????????????
        """
        feature_plane = get_feature_plane(self.board.fen())
        feature_plane = feature_plane[np.newaxis, :]
        policy, _ = self.model.predict(feature_plane, batch_size=1)

        candidates = {}
        #??????5???(??????)???????????????policy????????????
        if self.moves_cnt <= 5:
            legal_moves = self.board.legal_moves
            for move in legal_moves:
                move = move.uci()
                p = policy[0][self.move_hash[move]]
                candidates[move] = p
            x = sorted(candidates.items(), key=lambda x:x[1], reverse=True)
        else:
        #??????5????????????alpha-beta search?????????value?????????
            self.alpha_beta_search(self.board, self.search_depth, -self.INF, self.INF, 1)  #alpha=-INF, beta=INF, color=1???????????????
            for move in self.move_value:
                v = self.move_value[move]
                move = move.uci()
                p = policy[0][self.move_hash[move]]
                print(move, str(v), str(p))
                v = ((1 + v) ** 2) * p
                candidates[move] = (v, p)
            x = sorted(candidates.items(), key=lambda x:(x[1][0], x[1][1]), reverse=True)
           
        print('moves_cnt: ', self.moves_cnt)
        self.moves_cnt += 1 #??????+1
        self.move_value.clear()
        return x[0][0]  #??????move


    def alpha_beta_search(self, board, depth, alpha, beta, color):
        '''
        board???????????????
        depth?????????????????????
        alpha beta
        color?????????????????????
        '''
        #??????????????????????????????????????????INF
        if board.is_game_over():
            return -color*self.INF
        
        #???????????????????????????????????????value
        if depth == 0:
            if color == 1:
                return -self.valuation(chess.Board(first_person_view_fen(self.board.fen(), 1)))
            else:
                return self.valuation(board)

        #???policy????????????????????????4????????????????????????
        legal_moves_list = list(board.legal_moves)
        #print()

        policy_list = []
        if color == 1:
            feature_plane = convert_board_to_plane(board.fen())
            feature_plane = feature_plane[np.newaxis, :]
            policy, _ = self.model.predict(feature_plane, batch_size=1)

            policy = [first_person_view_policy(policy[0], is_black_turn(board.fen()))]
            policy_list = [ (move, policy[0][self.move_hash[move.uci()]]) for move in legal_moves_list]
            policy_list = sorted(policy_list, key=lambda x:x[1], reverse=True) #??????????????????
        else:
            for move in legal_moves_list:
                policy_list.append((move, 1))

        #?????????4???
        threshold = min(0.01, max([policy_v[1] for policy_v in policy_list]))
        lim = 5 if self.search_depth == depth else 10
        if self.search_depth == depth:
            threads = []
            for move, policy_value in (policy_list[:lim] if color == 1 else policy_list):
                if policy_value < threshold:
                    continue
                moves.append(move)
                board.push(move)
                tboard = chess.Board()
                tboard.set_fen(board.fen())
                tthread = MyThread(alpha_beta_search,(self, tboard, depth - 1, alpha, beta, -color))
                threads.append([tthread, tboard, move])
                board.pop()
            for t in threads:
                t[0].start()
            for t in threads:
                t[0].join()
            for tthread,tboard,move in threads:
                self.move_value[move] = tthread.get_result()
                if color == 1:
                    alpha = max(alpha, value)
                else:
                    beta = min(beta, value)
                if beta <= alpha:
                    break
        else:
            for move, policy_value in (policy_list[:lim] if color == 1 else policy_list):
                if policy_value < threshold:
                    continue

                board.push(move)

                value = self.alpha_beta_search(board, depth - 1, alpha, beta, -color)

                board.pop()
                if self.search_depth == depth:
                    self.move_value[move] = value
                    #print(move.uci())
                '''if depth == 1:
                    print(move.uci(), is_black_turn(board.fen()), ' ', board.fen(), 'policy=', _)'''
                if color == 1:
                    alpha = max(alpha, value)
                else:
                    beta = min(beta, value)
                if beta <= alpha:
                    break
        return alpha if color == 1 else beta
    
    def valuation(self, board):
        #??????value network???????????? (?????????????????????)
        feature_plane = get_feature_plane(board.fen())
        feature_plane = feature_plane[np.newaxis, :]
        value = self.value_model.predict(feature_plane, batch_size=1)
        #print(board.fen(), ' ', value[0][0])
        return int(10.0 * value[0][0])


def convert_black_uci(move):
    new_move = []
    for s in move:
        if s.isdigit():
            new_move.append(str(9 - int(s)))
        else:
            new_move.append(s)
    return ''.join(new_move)

def count_piece(board_fen):
    '''
    count many pieces left on the board
    '''
    cnt = 0
    for pos in board_fen:
        if pos.isalpha():
            cnt += 1
    return cnt
