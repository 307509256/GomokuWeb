#!/usr/bin/env python

from __future__ import print_function, division
import itertools, time, copy
import collections, random
import os, sys, pickle
import numba
import numpy as np

board_size = 15
estimate_level = 9
def strategy(state):
    """ AI's strategy """

    """ Information provided to you:

    state = (board, last_move, playing, board_size)
    board = (x_stones, o_stones)
    stones is a set contains positions of one player's stones. e.g.
        x_stones = {(8,8), (8,9), (8,10), (8,11)}
    playing = 0|1, the current player's index

    Your strategy will return a position code for the next stone, e.g. (8,7)
    """

    global board_size
    board, last_move, playing, board_size = state
    strategy.playing = playing
    initialize()

    other_player = int(not playing)
    my_stones = board[playing]
    opponent_stones = board[other_player]

    if last_move is None: # if it's the first move of the game
        # put the first stone in the center if it's the start of the game
        center = int((board_size-1)/2)
        best_move = (center, center)
        assert playing == 0
        strategy.started_from_beginning = True
        strategy.zobrist_code = strategy.zobrist_me[best_move]
        strategy.hist_states = [strategy.zobrist_code]
        if strategy.zobrist_code not in strategy.cachehigh:
            strategy.cachehigh[strategy.zobrist_code] = 0.5
        return (best_move[0]+1, best_move[1]+1)
    elif len(my_stones) == 0:
        assert playing == 1
        strategy.started_from_beginning = True
        strategy.zobrist_code = 0
        strategy.hist_states = []
    elif len(my_stones) == 1 and len(opponent_stones) == 1:
        assert playing == 0
        if not hasattr(strategy, 'started_from_beginning') or strategy.started_from_beginning == False:
            strategy.started_from_beginning = True
            my_first_move = list(my_stones)[0]
            strategy.zobrist_code = strategy.zobrist_me[my_first_move[0]-1, my_first_move[1]-1]
            strategy.hist_states = [strategy.zobrist_code]
            if strategy.zobrist_code not in strategy.cachehigh:
                strategy.cachehigh[strategy.zobrist_code] = 0.5

    last_move = (last_move[0]-1, last_move[1]-1)
    # update zobrist_code with opponent last move
    strategy.zobrist_code ^= strategy.zobrist_opponent[last_move]

    # build new state representation
    state = np.zeros(board_size**2, dtype=np.int32).reshape(board_size, board_size)
    for i,j in my_stones:
        state[i-1,j-1] = 1
    for i,j in opponent_stones:
        state[i-1,j-1] = -1

    # clear the U cache
    U_stone.cache = dict()

    alpha = -1.0
    beta = 2.0
    empty_spots_left = np.sum(state==0)
    best_move, best_q = best_action_q(state, strategy.zobrist_code, empty_spots_left, last_move, alpha, beta, 1, 0)

    # update zobrist_code with my move
    strategy.zobrist_code ^= strategy.zobrist_me[best_move]
    # store the win rate of this move
    if strategy.zobrist_code not in strategy.cachehigh:
        strategy.cachehigh[strategy.zobrist_code] = best_q

    state[best_move] = 1

    game_finished = False
    new_u = 0
    if i_win(state, best_move, 1):
        new_u = 1.0
        game_finished = True
    elif i_lost(state, 1):
        new_u = 0.0
        game_finished = True
    elif empty_spots_left <= 2:
        new_u = 0.5
        game_finished = True

    if game_finished and strategy.started_from_beginning is True:
        print("best_q = %f"%best_q)
        discount = 1.0
        for prev_state_zobrist_code in strategy.hist_states[::-1]:
            if prev_state_zobrist_code in strategy.n_visited:
                n_visited = strategy.n_visited[prev_state_zobrist_code]
                n_visited += 1
            else:
                n_visited = 1
            u = strategy.cachehigh[prev_state_zobrist_code]
            new_u = u + discount * (new_u - u) /    (n_visited+1) # this is the learning rate
            strategy.cachehigh[prev_state_zobrist_code] = new_u
            strategy.n_visited[prev_state_zobrist_code] = n_visited
            print("Updated U of %d from %f to %f"%(prev_state_zobrist_code, u, new_u))
            #discount *= discount_factor
        print("Updated win rate of %d states" % len(strategy.hist_states))
        strategy.started_from_beginning = False # we only update once
        finish()
    elif empty_spots_left > 100:
        # record the history states
        strategy.hist_states.append(strategy.zobrist_code)
    # return the best move
    return (best_move[0]+1, best_move[1]+1)



level_max_n = [20, 20, 12, 12, 8, 8, 6, 6, 4, 4, 4, 4, 4, 4, 4]
def best_action_q(state, zobrist_code, empty_spots_left, last_move, alpha, beta, player, level):
    "Return the optimal action for a state"

    if empty_spots_left == 0: # Board filled up, it's a tie
        return None, 0.5

    verbose = True if level == 0 else False
    #verbose = False
    n_moves = level_max_n[level]
    interested_moves = find_interesting_moves(state, last_move, player, n_moves, verbose)

    if len(interested_moves) == 1:
        current_move = interested_moves.pop()
        q = Q_stone(state, zobrist_code, empty_spots_left, current_move, alpha, beta, player, level)
        return current_move, q

    #best_move = (-1,-1) # admit defeat if all moves have 0 win rate
    best_move = interested_moves[0] # continue to play even I'm losing

    if player == 1:
        max_q = 0.0
        max_bonused = False
        bonus_q = 0.1
        for current_move in interested_moves:
            q = Q_stone(state, zobrist_code, empty_spots_left, current_move, alpha, beta, player, level+1)
            if q > alpha: alpha = q
            if level == 0:
                next_zobrist_code = zobrist_code ^ strategy.zobrist_me[current_move]
                if next_zobrist_code not in strategy.n_visited or strategy.n_visited[next_zobrist_code] < 5:
                    if q + bonus_q > max_q:
                        max_q = q + bonus_q
                        best_move = current_move
                        max_bonused = True
                elif q > max_q:
                    max_q = q
                    best_move = current_move
                    max_bonused = False
            else:
                if q > max_q:
                    max_q = q
                    best_move = current_move
            if max_q >= 1.0 or beta <= alpha:
                break
        if max_bonused:
            best_q = max_q - bonus_q
        else:
            best_q = max_q
    elif player == -1:
        min_q = 1.0
        for current_move in interested_moves:
            q = Q_stone(state, zobrist_code, empty_spots_left, current_move, alpha, beta, player, level+1)
            if q < beta: beta = q
            if q < min_q:
                min_q = q
                best_move = current_move
            if q == 0.0 or beta <= alpha:
                break
        best_q = min_q
    return best_move, best_q

@numba.jit(nopython=True, nogil=True)
def find_interesting_moves(state, last_move, player, n_moves, verbose=False):
    """ Look at state and find the interesing n_move moves.
    input:
    -------
    state: numpy.array board_size x board_size
    last_move: opponent's last move
    player: 1 or -1, the current player
    n_moves: int, desired number of interesing moves

    output:
    -------
    interested_moves: list of moves from highest interest to low
        *note1: if limited, return a list of one move [(r,c)]
        *note2: if a high interest move found (>256), n_move will += 1
    """
    force_to_block = False
    exist_will_win_move = False
    directions = ((1,1), (1,0), (0,1), (1,-1))
    n_moves_found = 0
    interested_moves = []
    move_interests = []
    for r in range(board_size):
        for c in range(board_size):
            if state[r,c] != 0: continue
            related_to_last_move = False
            interest_value = 0
            my_hard_4 = 0
            for dr, dc in directions:
                my_line_length = 1 # last_move
                opponent_line_length = 1
                # try to extend in the positive direction (max 4 times)
                ext_r = r
                ext_c = c
                skipped_1 = 0
                my_blocked = False
                opponent_blocked = False
                for i in range(4):
                    ext_r += dr
                    ext_c += dc
                    if ext_r < 0 or ext_r >= board_size or ext_c < 0 or ext_c >= board_size:
                        break
                    elif state[ext_r, ext_c] == player:
                        if my_blocked is True:
                            break
                        else:
                            my_line_length += 1
                            opponent_blocked = True
                    elif state[ext_r, ext_c] == -player:
                        if opponent_blocked is True:
                            break
                        else:
                            opponent_line_length += 1
                            my_blocked = True
                            if ext_r == last_move[0] and ext_c == last_move[1]:
                                related_to_last_move = True
                    elif skipped_1 is 0:
                        skipped_1 = i + 1 # allow one skip and record the position of the skip
                    else:
                        break
                # the backward counting starts at the furthest "unskipped" stone
                forward_my_open = False
                forward_opponent_open = False
                if skipped_1 == 0:
                    my_line_length_back = my_line_length
                    opponent_line_length_back = opponent_line_length
                elif skipped_1 == 1:
                    my_line_length_back = 1
                    opponent_line_length_back = 1
                    forward_my_open = True
                    forward_opponent_open = True
                else:
                    if my_blocked is False:
                        my_line_length_back = skipped_1
                        opponent_line_length_back = 1
                        forward_my_open = True
                    else:
                        my_line_length_back = 1
                        opponent_line_length_back = skipped_1
                        forward_opponent_open = True
                my_line_length_no_skip = my_line_length_back
                opponent_line_length_no_skip = opponent_line_length_back

                # backward is a little complicated, will try to extend my stones first
                ext_r = r
                ext_c = c
                skipped_2 = 0
                opponent_blocked = False
                for i in range(5-my_line_length_no_skip):
                    ext_r -= dr
                    ext_c -= dc
                    if ext_r < 0 or ext_r >= board_size or ext_c < 0 or ext_c >= board_size:
                        break
                    elif state[ext_r, ext_c] == player:
                        my_line_length_back += 1
                        opponent_blocked = True
                    elif skipped_2 is 0 and state[ext_r, ext_c] == 0:
                        skipped_2 = i + 1
                    else:
                        break
                # see if i'm winning
                if my_line_length_back == 5:
                    return [(r,c)]
                # extend my forward line length to check if there is hard 4
                if skipped_2 is 0:
                    my_line_length += my_line_length_back - my_line_length_no_skip
                else:
                    my_line_length += skipped_2 - 1
                # notice that here the forward length can exceed 5 after extension, but it should be at max 4
                if my_line_length > 4:
                    my_line_length = 4

                backward_my_open = True if skipped_2 > 0 else False
                backward_opponent_open = False
                # then try to extend the opponent
                if opponent_blocked is True:
                    if skipped_2 == 1:
                        backward_opponent_open = True
                else:
                    ext_r = r
                    ext_c = c
                    skipped_2 = 0
                    for i in range(5-opponent_line_length_no_skip):
                        ext_r -= dr
                        ext_c -= dc
                        if ext_r < 0 or ext_r >= board_size or ext_c < 0 or ext_c >= board_size:
                            break
                        elif state[ext_r, ext_c] == -player:
                            opponent_line_length_back += 1
                            if ext_r == last_move[0] and ext_c == last_move[1]:
                                related_to_last_move = True
                        elif skipped_2 is 0 and state[ext_r, ext_c] == 0:
                            skipped_2 = i + 1
                        else:
                            break

                    # extend my forward line length to check if there is hard 4
                    if skipped_2 is 0:
                        opponent_line_length += opponent_line_length_back - opponent_line_length_no_skip
                    else:
                        opponent_line_length += skipped_2 - 1
                        backward_opponent_open = True
                        # here if opponent_line_length_back == 5, skipped_2 will be 0 and this flag won't be True
                        # but it do not affect our final result, because we have to block this no matter if it's open
                    # notice that here the forward length can exceed 5 after extension, but it should be at max 4
                    if opponent_line_length > 4:
                        opponent_line_length = 4

                # check if we have to block this
                if opponent_line_length_back == 5:
                    interested_moves = [(r,c)]
                    force_to_block = True
                elif force_to_block is False:
                    # if I will win after this move, I won't consider other moves
                    if forward_my_open is True and my_line_length == 4:
                        my_hard_4 += 1
                    if backward_my_open is True and my_line_length_back == 4:
                        my_hard_4 += 1
                    if my_hard_4 >= 2:
                        interested_moves = [(r,c)]
                        exist_will_win_move = True
                if force_to_block is False and exist_will_win_move is False:
                    # compute the interest_value for other moves
                    if forward_my_open is True:
                        interest_value += my_line_length ** 4
                    if backward_my_open is True:
                        interest_value += my_line_length_back ** 4
                    if forward_opponent_open is True:
                        interest_value += opponent_line_length ** 4
                    if backward_opponent_open is True:
                        interest_value += opponent_line_length_back ** 4
            # after looking at all directions, put this move in orderred list interested_moves and move_interests
            if force_to_block is False and exist_will_win_move is False:
                if interest_value > 256 and related_to_last_move is True:
                    n_moves += 1
                if n_moves_found == 0:
                    interested_moves.append((r,c))
                    move_interests.append(interest_value)
                    n_moves_found += 1
                elif n_moves_found < n_moves:
                    i = n_moves_found - 1
                    while True:
                        if interest_value < move_interests[i] or i < 0:
                            break
                        i -= 1
                    interested_moves.insert(i+1, (r,c))
                    move_interests.insert(i+1, interest_value)
                    n_moves_found += 1
                elif interest_value > move_interests[-1]:
                    interested_moves.pop()
                    move_interests.pop()
                    i = n_moves_found - 1
                    while True:
                        if interest_value < move_interests[i] or i < 0:
                            break
                        i -= 1
                    interested_moves.insert(i+1, (r,c))
                    move_interests.insert(i+1, interest_value)

    # all moves have been investigated now see if we have to block first
    if verbose is True:
        if force_to_block is True or exist_will_win_move is True:
            print(interested_moves[0][0],interested_moves[0][1] , "Only One")
        else:
            print("There are", n_moves, "interested_moves")
            for i in range(n_moves):
                print(interested_moves[i][0],interested_moves[i][1],'  :  ', move_interests[i])
    return interested_moves


def Q_stone(state, zobrist_code, empty_spots_left, current_move, alpha, beta, player, level):
    # update the state
    state[current_move] = player
    # update the zobrist code for the new state
    if player == 1:
        move_code = strategy.zobrist_me[current_move]
    else:
        move_code = strategy.zobrist_opponent[current_move]
    new_zobrist_code = zobrist_code ^ move_code

    result = U_stone(state, new_zobrist_code, empty_spots_left-1, current_move, alpha, beta, player, level)
    # revert the changes for the state
    state[current_move] = 0
    return result

def U_stone(state, zobrist_code, empty_spots_left, last_move, alpha, beta, player, level):
    try:
        return strategy.cachehigh[zobrist_code]
    except:
        pass
    try:
        return U_stone.cache[zobrist_code]
    except:
        pass


    if i_will_win(state, last_move, player):
        return 1.0 if player == 1 else 0.0
    elif level >= estimate_level:
        result = estimate_U(state, player)
    else:
        best_move, best_q = best_action_q(state, zobrist_code, empty_spots_left, last_move, alpha, beta, -player, level)
        result = best_q
    U_stone.cache[zobrist_code] = result
    #if level == 1 and empty_spots_left > 200: # encourage exploration
        #result += (1.0-result) * np.random.random() * 0.4
    return result


@numba.jit(nopython=True, nogil=True)
def estimate_U(state, player):
    u = 0.0
    my_max_n = 0
    opponent_max_n = 0
    for i in range(board_size):
        for j in range(board_size):
            # horizontal wins --
            if j <= board_size - 5:
                my_blocked, opponent_blocked = False, False
                my_n, opponent_n = 0, 0
                for k in range(5):
                    if state[i, j+k] == -1:
                        my_blocked = True
                        opponent_n += 1
                    elif state[i, j+k] == 1:
                        opponent_blocked = True
                        my_n += 1
                    if my_blocked is True and opponent_blocked is True:
                        break
                if my_blocked is False:
                    u += 3 ** my_n
                    if my_n > my_max_n:
                        my_max_n = my_n
                if opponent_blocked is False:
                    u -= 3 ** opponent_n
                    if opponent_n > opponent_max_n:
                        opponent_max_n = opponent_n
            # vertical wins |
            if i <= board_size - 5:
                my_blocked, opponent_blocked = False, False
                my_n, opponent_n = 0, 0
                for k in range(5):
                    if state[i+k, j] == -1:
                        my_blocked = True
                        opponent_n += 1
                    elif state[i+k, j] == 1:
                        opponent_blocked = True
                        my_n += 1
                    if my_blocked is True and opponent_blocked is True:
                        break
                if my_blocked is False:
                    u += 3 ** my_n
                    if my_n > my_max_n:
                        my_max_n = my_n
                if opponent_blocked is False:
                    u -= 3 ** opponent_n
                    if opponent_n > opponent_max_n:
                        opponent_max_n = opponent_n
            # left oblique wins /
            if i <= board_size - 5 and j >= 4:
                my_blocked, opponent_blocked = False, False
                my_n, opponent_n = 0, 0
                for k in range(5):
                    if state[i+k, j-k] == -1:
                        my_blocked = True
                        opponent_n += 1
                    elif state[i+k, j-k] == 1:
                        opponent_blocked = True
                        my_n += 1
                    if my_blocked is True and opponent_blocked is True:
                        break
                if my_blocked is False:
                    u += 3 ** my_n
                    if my_n > my_max_n:
                        my_max_n = my_n
                if opponent_blocked is False:
                    u -= 3 ** opponent_n
                    if opponent_n > opponent_max_n:
                        opponent_max_n = opponent_n
            # right oblique wins \
            if i <= board_size - 5 and j <= board_size - 5:
                my_blocked, opponent_blocked = False, False
                my_n, opponent_n = 0, 0
                for k in range(5):
                    if state[i+k, j+k] == -1:
                        my_blocked = True
                        opponent_n += 1
                    elif state[i+k, j+k] == 1:
                        opponent_blocked = True
                        my_n += 1
                    if my_blocked is True and opponent_blocked is True:
                        break
                if my_blocked is False:
                    u += 3 ** my_n
                    if my_n > my_max_n:
                        my_max_n = my_n
                if opponent_blocked is False:
                    u -= 3 ** opponent_n
                    if opponent_n > opponent_max_n:
                        opponent_max_n = opponent_n
    if player == 1: # next move is opponent
        longer = 2 * (3 **opponent_max_n)  # one of the longest can get 1 longer
        block = 3 ** my_max_n
        u -= max(longer, block)
    else: # next move is me
        longer = 2 * (3 ** my_max_n)
        block = 3 ** opponent_max_n
        u += max(longer, block)

    if u > 0:
        result = 1.0 - 0.5 * np.exp(-u**2 * 0.0001)
    else:
        result = 0.5 * np.exp(-u**2 * 0.0001)
    return result


@numba.jit(nopython=True,nogil=True)
def i_win(state, last_move, player):
    """ Return true if I just got 5-in-a-row with last_move """
    r, c = last_move
    # try all 4 directions, the other 4 is included
    directions = [(1,1), (1,0), (0,1), (1,-1)]
    for dr, dc in directions:
        line_length = 1 # last_move
        # try to extend in the positive direction (max 4 times)
        ext_r = r
        ext_c = c
        for _ in range(4):
            ext_r += dr
            ext_c += dc
            if ext_r < 0 or ext_r >= board_size or ext_c < 0 or ext_c >= board_size:
                break
            elif state[ext_r, ext_c] == player:
                line_length += 1
            else:
                break
        if line_length is 5:
            return True # 5 in a row
        # try to extend in the opposite direction
        ext_r = r
        ext_c = c
        for _ in range(5-line_length):
            ext_r -= dr
            ext_c -= dc
            if ext_r < 0 or ext_r >= board_size or ext_c < 0 or ext_c >= board_size:
                break
            elif state[ext_r, ext_c] == player:
                line_length += 1
            else:
                break
        if line_length is 5:
            return True # 5 in a row
    return False

@numba.jit(nopython=True,nogil=True)
def i_lost(state, player):
    for r in range(board_size):
        for c in range(board_size):
            if state[r,c] == 0 and i_win(state, (r,c), -player):
                return True
    return False

@numba.jit(nopython=True,nogil=True)
def i_will_win(state, last_move, player):
    """ Return true if I will win next step if the opponent don't have 4-in-a-row.
    Winning Conditions:
        1. 5 in a row.
        2. 4 in a row with both end open. (free 4)
        3. 4 in a row with one missing stone x 2 (hard 4 x 2)
     """
    r, c = last_move
    # try all 4 directions, the other 4 is equivalent
    directions = [(1,1), (1,0), (0,1), (1,-1)]
    n_hard_4 = 0 # number of hard 4s found
    for dr, dc in directions:
        #print(dr, dc)
        line_length = 1 # last_move
        # try to extend in the positive direction (max 4 times)
        ext_r = r
        ext_c = c
        skipped_1 = 0
        for i in range(4):
            ext_r += dr
            ext_c += dc
            if ext_r < 0 or ext_r >= board_size or ext_c < 0 or ext_c >= board_size:
                break
            elif state[ext_r, ext_c] == player:
                line_length += 1
            elif skipped_1 is 0 and state[ext_r, ext_c] == 0:
                skipped_1 = i+1 # allow one skip and record the position of the skip
            else:
                break
        if line_length is 5:
            return True # 5 in a row
        #print("Forward line_length",line_length)
        # try to extend in the opposite direction
        ext_r = r
        ext_c = c
        skipped_2 = 0
        # the backward counting starts at the furthest "unskipped" stone
        if skipped_1 is not 0:
            line_length_back = skipped_1
        else:
            line_length_back = line_length
        line_length_no_skip = line_length_back
        for i in range(5-line_length_back):
            ext_r -= dr
            ext_c -= dc
            if ext_r < 0 or ext_r >= board_size or ext_c < 0 or ext_c >= board_size:
                break
            elif state[ext_r, ext_c] == player:
                line_length_back += 1
            elif skipped_2 is 0 and state[ext_r, ext_c] == 0:
                skipped_2 = i + 1
            else:
                break
        #print("Backward line_length",line_length_back)
        if line_length_back is 5:
            return True # 5 in a row
        if line_length_back == 4 and skipped_2 is not 0:
            n_hard_4 += 1 # backward hard 4
            if n_hard_4 == 2:
                return True # two hard 4

        #print("back n_hard_4 = ", n_hard_4)
        # extend the forward line to the furthest "unskipped" stone
        #print("line_length_back", line_length_back)
        if skipped_2 is 0:
            line_length += line_length_back - line_length_no_skip
        else:
            line_length += skipped_2 - 1
        if line_length >= 4 and skipped_1 is not 0:
            n_hard_4 += 1 # forward hard 4
            if n_hard_4 == 2:
                return True # two hard 4 or free 4
        #print('total n_hard_4', n_hard_4)
    return False

def initialize():
    color = 'black' if strategy.playing == 0 else 'white'
    color = os.path.join(sys.path[0],'app','AI',color)
    # initialize zobrist for u caching
    if not hasattr(strategy, 'zobrist_me'):
        np.random.seed(19890328) # use the same random matrix for storing
        strategy.zobrist_me = np.random.randint(np.iinfo(np.int64).max, size=board_size**2).reshape(board_size,board_size)
        strategy.zobrist_opponent = np.random.randint(np.iinfo(np.int64).max, size=board_size**2).reshape(board_size,board_size)
        strategy.zobrist_code = np.random.randint(np.iinfo(np.int64).max)
        # reset the random seed to random for other functions
        np.random.seed()
    if not hasattr(strategy, 'cachehigh'):
        filename = color + '.cachehigh'
        if os.path.exists(filename):
            strategy.cachehigh = pickle.load(open(filename, 'rb'))
            print("Successfully loaded %d previously computed win rates"%len(strategy.cachehigh))
        else:
            strategy.cachehigh = dict()
    if not hasattr(strategy, 'n_visited'):
        filename = color + '.n_visited'
        if os.path.exists(filename):
            strategy.n_visited = pickle.load(open(filename, 'rb'))
            print("Successfully loaded %d previously computed n_visited"%len(strategy.n_visited))
        else:
            strategy.n_visited = dict()
    if not hasattr(best_action_q, 'move_interest_values'):
        best_action_q.move_interest_values = np.zeros(board_size**2, dtype=np.float32).reshape(board_size,board_size)

def finish():
    color = 'black' if strategy.playing == 0 else 'white'
    color = os.path.join(sys.path[0],'app','AI', color)
    filename = color + '.cachehigh'
    pickle.dump(strategy.cachehigh, open(filename, 'wb'))
    print("Successfully saved %d U(s) to %s"%(len(strategy.cachehigh), filename))

    filename = color + '.n_visited'
    pickle.dump(strategy.n_visited, open(filename, 'wb'))
    print("Successfully saved %d N(s) to %s"%(len(strategy.n_visited), filename))

def board_show(stones):
    if isinstance(stones, np.ndarray):
        stones = {(s1,s2) for s1, s2 in stones}
    print(' '*4 + ' '.join([chr(97+i) for i in xrange(board_size)]))
    print (' '*3 + '='*(2*board_size))
    for x in xrange(1, board_size+1):
        row = ['%2s|'%x]
        for y in xrange(1, board_size+1):
            if (x-1,y-1) in stones:
                c = 'x'
            else:
                c = '-'
            row.append(c)
        print (' '.join(row))

def print_state(state):
    assert isinstance(state, np.ndarray)
    print(' '*4 + ' '.join([chr(97+i) for i in xrange(board_size)]))
    print (' '*3 + '='*(2*board_size))
    for x in xrange(1, board_size+1):
        row = ['%2s|'%x]
        for y in xrange(1, board_size+1):
            if state[x-1,y-1] == 1:
                c = 'o'
            elif state[x-1,y-1] == -1:
                c = 'x'
            else:
                c = '-'
            row.append(c)
        print (' '.join(row))


def check():
    global board_size
    board_size = 15
    state = np.zeros(board_size**2, dtype=np.int32).reshape(board_size, board_size)
    # check if i_win() is working properly
    state[zip(*[(8,9), (8,11), (8,8), (8,10), (8,12)])] = 1
    assert i_win(state, (8,10), 1) == True
    state.fill(0)
    state[zip(*[(8,10), (9,11), (8,8), (9,12), (7,9), (10,9), (11,12), (11,13)])] = 1
    assert i_win(state, (10,12), 1) == True
    state.fill(0)
    state[zip(*[(8,10), (8,12), (8,8), (9,12), (7,9), (10,9), (11,12), (11,13)])] = 1
    assert i_win(state, (10,12), 1) == False
    # check if i_will_win() is working properly
    # o - x x X x - o
    state.fill(0)
    state[zip(*[(8,9), (8,11), (8,8)])] = 1
    state[zip(*[(8,6), (8,13)])] = -1
    assert i_will_win(state, (8, 10), 1) == True

    #
    state.fill(0)
    state[zip(*[(7,7), (7,8), (9,11)])] = 1
    state[zip(*[(6,8), (7,9)])] = -1
    print(state)
    assert i_will_win(state, (8,10), -1) == False
    ## o - x x X x o
    #assert i_will_win({(8,9), (8,11), (8,8)}, {(8,6), (8,12)}, (8,10)) == False
    ## o - x x X o
    ##         x
    ##
    ##         x
    ##         x
    #assert i_will_win({(8,9), (8,8), (9,10), (11,10), (12,10)}, {(8,6), (8,11)}, (8,10)) == False
    ## o - x x X x o
    ##         x
    ##
    ##         x
    ##         x
    #assert i_will_win({(8,9), (8,8), (9,10), (11,10), (12,10)}, {(8,6), (8,11)}, (8,10)) == False
    ## o - x x X x o
    ##       x
    ##
    ##   x
    ## x
    #assert i_will_win({ (8,8), (8,9), (8,11), (9,9), (11,7), (12,6)}, {(8,6), (8,12)}, (8,10)) == True
    ## | x x x X - x x x - - o
    #assert i_will_win({(8,1), (8,2), (8,0), (8,9), (8,7), (8,8)}, {(8,10)}, (8,3)) == False
    ## | x x - x X x x o
    #assert i_will_win({(8,1), (8,2), (8,4), (8,6), (8,7)}, {(8,8)}, (8,5)) == False
    ## | x x - x X - x x o
    #assert i_will_win({(8,1), (8,2), (8,4), (8,7), (8,8)}, {(8,9)}, (8,5)) == True
    ## | x x x - X - x x x o
    #assert i_will_win({(8,1), (8,2), (8,3), (8,7), (8,8), (8,9)}, {(8,10)}, (8,5)) == True
    ## | x - x X x - x o
    #assert i_will_win({(8,1), (8,3), (8,5), (8,7)}, {(8,8)}, (8,4)) == True

    #assert i_will_win({(8,8), (8,10), (9,9), (11,7), (11,9)}, {(7,7), (7,9), (8,7), (10,8), (11,8)}, (8,9)) == False
    print("All check passed!")

if __name__ == '__main__':
    import pickle
    state = pickle.load(open('debug.state','rb'))
    board, last_move, playing, board_size = state
    player_stones = board[playing]
    other = int(not playing)
    ai_stones = board[other]
    player_move = (8,9)
    player_stones.add(player_move)
    state = (player_stones, ai_stones), player_move, other, board_size


    strategy(state)
    #import time
    #check()
    #test3()
    #benchmark()
    #benchmark2()
