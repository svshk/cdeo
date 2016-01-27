import utils.cat_parser as cat_parser
import utils.utils as utils
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
import numpy as np
import random
import copy
import cdeo_config
import itertools
import nltk.stem.porter as porter
reload(utils)

'''
def linkEventEntity(doc, targetEntityText):
    # Do something simple. Link event and entity if they are in the same sentence.
    res = list()
    for en in doc.Markables.ENTITY_MENTION:
        if en.get_type() == targetEntityText:
            entity_t_id = en.get_token_anchor()[0].t_id
            entity_sentence = utils.getToken(doc, entity_t_id).sentence
            for ev in doc.Markables.EVENT_MENTION:
                event_t_id = ev.get_token_anchor()[0].t_id
                event_sentence = utils.getToken(doc, event_t_id).sentence
                if entity_sentence == event_sentence:
                    if res.count(ev.m_id) == 0:
                        res.append(ev.m_id)

    return res
'''
def linkEventEntityRuleBased(doc, targetEntityText):
    ''' Loop over events and pair <targetEntityText> entity if it is the closest entity in the same (or nearest 2) sentence'''
    res = list()
    # loop over events
    for ev in doc.Markables.EVENT_MENTION:
        event_t_id = ev.get_token_anchor()[0].t_id
        event_sentence = utils.getToken(doc, event_t_id).sentence
        # loop over all entitites to find the nearest one
        best_entity = []
        best_dist = 1000
        for en in doc.Markables.ENTITY_MENTION:
            entity_t_id = en.get_token_anchor()[0].t_id
            entity_sentence = utils.getToken(doc, entity_t_id).sentence
            if event_sentence == entity_sentence: # or event_sentence == entity_sentence+1 or event_sentence == entity_sentence-1: # check if in the same sentence
                if abs(entity_t_id - event_t_id) < best_dist:
                    best_dist = abs(entity_t_id - event_t_id)
                    best_entity = en
        # pair event to entity if entity of correct type
        try:
            if best_entity.get_type() == targetEntityText: 
                if res.count(ev.m_id) == 0:
                    res.append(ev.m_id)
        except AttributeError:
            pass
    return res
    
def linkEventEntityML(clf, doc, targetEntityList, syntactic_features):
    # prep dictionary
    res = dict()
    for targetEntity in targetEntityList:
        res[targetEntity] = []
        
    # loop over events and predict for each event
    for event in doc.Markables.EVENT_MENTION:
        predictedEntityList = predictEventEntityLink(clf, doc, event, targetEntityList, syntactic_features)
        for predictedEntity in predictedEntityList:
            if targetEntityList.count(predictedEntity): # check if the predicted entity is not 'unknown'
                res[predictedEntity].append(event.m_id)
    return res
    
def trainEventEntityClassifier(collection_train_list, syntactic_features):
    '''Takes a collection that has been annotated with the gold timeline and a list of target entities. 
    Returns a collection of documents with the EVENT elements annotated with the gold Entity. Returns a classifier for the event-entity links.'''
    
    # Build the feature and label arrays
    featuresList = list()
    labelsList = list() 
    for tup in collection_train_list:
        (collection, targetEntityList) = tup
        for doc in collection:
            for event in doc.Markables.EVENT_MENTION:
                '''
                # NB: we need to balance the classes, so we use one class '1' and one class '0'
                class_0_list = copy.deepcopy(targetEntityList)
                try:
                    class_0_list.remove(event.get_linkedEntityName())
                except ValueError:
                    print class_0_list, event.get_linkedEntityName(), utils.getEventText(doc, event), event.m_id, doc.get_doc_id()
                    continue
                wanted_list = [event.get_linkedEntityName(), class_0_list[random.randint(0,len(class_0_list)-1)]]
                '''
                wanted_list = targetEntityList
                for targetEntity in wanted_list:
                    thisEntityFeatureList = getLinkFeatures(doc, event, targetEntity, syntactic_features)
                    featuresList += thisEntityFeatureList
                    if event.get_linkedEntityName() == targetEntity: # true label
                        labelsList += [1]*len(thisEntityFeatureList)
                    else:                                            # false label
                        labelsList += [0]*len(thisEntityFeatureList)

    '''
    decision_function(X)	Predict confidence scores for samples.
    densify()	Convert coefficient matrix to dense array format.
    fit(X, y)	Fit the model according to the given training data.
    fit_transform(X[, y])	Fit to data, then transform it.
    get_params([deep])	Get parameters for this estimator.
    predict(X)	Predict class labels for samples in X.
    predict_log_proba(X)	Log of probability estimates.
    predict_proba(X)	Probability estimates.
    score(X, y[, sample_weight])	Returns the mean accuracy on the given test data and labels.
    set_params(**params)	Set the parameters of this estimator.
    sparsify()	Convert coefficient matrix to sparse format.
    transform(X[, threshold])	Reduce X to its most important features.
    '''

    # solver : {'newton-cg', 'lbfgs', 'liblinear'}
    clf = LogisticRegression(solver='lbfgs', C=0.5, penalty='l2', tol=1e-5, class_weight='auto', fit_intercept=True)
    #clf = LogisticRegression(solver='liblinear', C=0.5, penalty='l2', tol=1e-5, class_weight='auto', fit_intercept=True)
    #clf = SVC(probability=True, kernel='rbf', class_weight='auto', tol=1e-4)
    print '#'
    print len(labelsList), labelsList[0]
    print len(featuresList), np.size(featuresList[0])
    clf.fit(featuresList, labelsList)

    print len(featuresList), np.sum(labelsList)

    return clf
    
def predictEventEntityLink(clf, doc, event, targetEntityList, syntactic_features):
    '''Given a trained classifier predict the Entity associated with the Event'''
    features = list()
    labels = list()
    for targetEntity in targetEntityList:
        thisEntityFeatures = getLinkFeatures(doc, event, targetEntity, syntactic_features)
        features += thisEntityFeatures
        labels += [targetEntity]*len(thisEntityFeatures)
    if len(features) > 0:
        predicted_prob = clf.predict_proba(features)
        predicted_prob = [x[1] for x in predicted_prob] # get the '1' label in the 2nd column
        imax = np.argmax(predicted_prob)
        #print predicted_prob, labels
        isorted = list(reversed(utils.myargsort(predicted_prob)))
        imax = isorted[0]
            
        if predicted_prob[imax] > cdeo_config.getConfig('event_entity_link_threshold'): # increase to increase precision at the cost of recall
            res = [labels[imax]]
        else:
            return ['unknown']
        
        # if we have another entity label with a high probability of a link (it could be a conjunction)
        #if len(predicted_prob) > 1:
        #    i2nd = isorted[1]
        #    if predicted_prob[i2nd] >= 0.5:
        #        res.append(labels[i2nd])
        return res
    else:
        return ['unknown'] # we could not exctract any features
        
    
def getLinkFeatures(doc, event, targetEntity, syntactic_features):
    '''Get a list of feature vectors for the event and the target entity only if they are in the same sentence. Return an empty list otherwise.'''
    sentence_flag = False
    #features_init = np.zeros(500) # features
    features = np.zeros(500) # features
    
    event_t_id = event.get_token_anchor()[0].t_id
    event_sentence = utils.getToken(doc, event_t_id).sentence
    for en in doc.Markables.ENTITY_MENTION:
        if en.get_type() == targetEntity: 
            
            entity_t_id = en.get_token_anchor()[0].t_id # use the first token of the entity trigger
            entity_sentence = utils.getToken(doc, entity_t_id).sentence
            entity_text = utils.getEntityText(doc, en)
            
            ind = 0
            if event_sentence == entity_sentence:
                features[ind] = 1
            ind += 1
            if event_sentence - entity_sentence == -1:
                features[ind] = 1
            ind += 1
            if event_sentence - entity_sentence == 1:
                features[ind] = 1
            ind += 1

            # bins of 1 unit token distance
            d = event_t_id - entity_t_id
            n = 20
            bin_size = 1.0
            if abs(d) <= n:
                thisBin = int(np.fix(d/bin_size))
                features[ind+thisBin+int(n/bin_size)] = 1
            ind += 2*(n/bin_size)+1  # 21

            # bins of 2 unit token distance
            d = event_t_id - entity_t_id
            n = 20
            bin_size = 2.0
            if abs(d) <= n:
                thisBin = int(np.fix(d/bin_size))
                features[ind+thisBin+int(n/bin_size)] = 1
            ind += 2*(n/bin_size)+1  # 21

            # bins of 5 unit token distance
            d = event_t_id - entity_t_id
            n = 40
            bin_size = 5.0
            if abs(d) <= n:
                thisBin = int(np.fix(d/bin_size))
                features[ind+thisBin+int(n/bin_size)] = 1
            ind += 2*(n/bin_size)+1  # 17

            # bins of 10 unit token distance
            d = event_t_id - entity_t_id
            n = 50
            bin_size = 10.0
            if abs(d) <= n:
                thisBin = int(np.fix(d/bin_size))
                features[ind+thisBin+int(n/bin_size)] = 1
            ind += 2*(n/bin_size)+1  # 11
            
            # syntactic dependencies
            '''
            <dep type="nsubj">
              <governor idx="2">unveils</governor>
              <dependent idx="1">Apple</dependent>
            </dep>
            <dep type="dobj">
              <governor idx="2">unveils</governor>
              <dependent idx="3">iPhone</dependent>
            </dep>
            '''
            if event_sentence == entity_sentence:
                wanted_sentence = event_sentence
                deps = doc.root[0][0][wanted_sentence][2] # NB: note the indexing! The title is a separate sentence in CAT but it's merged into 1st sentence in Stanford NLP parse.

                for dep in deps:
                    if utils.getEventTextFull(doc, event).split('_').count(dep[0].text.lower()) and entity_text.split(' ').count(dep[1].text):
                        for i in range(len(syntactic_features)):
                            if dep.values()[0] == syntactic_features[i]:
                                #print  str(ind+i) + ': [' + targetEntity + ']', dep[1].text, dep[0].text, ':' + syntactic_features[i], event_sentence, doc.get_doc_id()
                                features[ind+i] = 1  
            #ind += len(syntactic_features)
                
    return features
    
def extractSyntacticFeatures(collection):
    res = list()
    for doc in collection:
        for event in doc.Markables.EVENT_MENTION:
            event_t_id = event.get_token_anchor()[0].t_id
            event_sentence = utils.getToken(doc, event_t_id).sentence
            event_text = utils.getEventTextFull(doc, event)
            for entity in doc.Markables.ENTITY_MENTION: 
                entity_t_id = entity.get_token_anchor()[-1].t_id # use the last token of the entity trigger
                entity_sentence = utils.getToken(doc, entity_t_id).sentence
                entity_text = utils.getEntityText(doc, entity)
                if entity.get_type() == event.get_linkedEntityName() and event_sentence == entity_sentence: # only for gold event-entity links

                    wanted_sentence = event_sentence
                    try:
                        deps = doc.root[0][0][wanted_sentence][2] # NB: note the indexing! The title is a separate sentence in CAT but it's merged into 1st sentence in Stanford NLP parse.
                    except IndexError:
                        pass

                    for dep in deps:
                        if event_text.split('_').count(dep[0].text.lower()) and entity_text.split(' ').count(dep[1].text):
                            if res.count(dep.values()[0]) == 0:
                                res.append(dep.values()[0])
    #print res
    return res

def structuredPredictionTraining(collection_train_list, syntactic_features):
    '''Takes a collection that has been annotated with the gold timeline. Returns a classifier for the event-timex3 links.'''
    # initiate the weights vector
    w = np.zeros(510)
    wa = np.zeros(510)
    c = 1.0
    lrate = 1
        
    trainError = list()
    wanted_type = ['DATE','TIME']
    for i in range(15): # number of iterations
        print 'Structured Perceptron Iteration: ', i
        lrate = 0.9*lrate
        # do the prep
        # TBD: speed this up by saving
        for tup in collection_train_list:
            (collection, targetEntityList) = tup
            #random.shuffle(collection)
            for doc in collection:
                
                # get a list of all target entities
                #allEntities = [None] # allow for a possibility of not matching with an actual timex 
                #for e in doc.Markables.ENTITY_MENTION:
                #    allEntities.append(e.m_id)

                # get lists of linked events and entities
                linkedEvents = list()
                linkedEntities = list()
                for event in doc.Markables.EVENT_MENTION:
                    goldEntity = event.get_linkedEntityName()
                    if goldEntity == None: # is this used?
                        #continue
                        linkedEvents.append(event)
                        linkedEntities.append(None)
                    else:
                        linkedEvents.append(event)
                        linkedEntities.append(goldEntity)
                        
                        

                # for each document we have:
                # - a list of events in linkedEvents
                # - a corresponding list (training set) of linked timex m_id in linkedTimex
                # - a list of all timex in allTimex
                # - getLinkFeatures(doc, event, m_id, syntactic_features) will get the features for every event-timex pair
                # - getGlobalFeatures(doc, (prev_event, t0), (event, t1)) will get the features for consecutive event-timex pairs
                # - argmaxEventTIMEX(doc, event, allTimex, w)
                
                # precompute features
                local_feat_dict = dict()
                for event in linkedEvents:
                    for entity in targetEntityList:
                        local_feat_dict[(event, entity)] = getLinkFeatures(doc, event, entity, syntactic_features)
                        
                global_feat_dict = dict()
                for e in range(1, len(linkedEvents)):
                    prev_event = linkedEvents[e-1]
                    event = linkedEvents[e]
                    for e0 in targetEntityList:
                        for e1 in targetEntityList:
                            global_feat_dict[((prev_event, e0),(event, e1))] = getGlobalFeatures(doc, (prev_event, e0), (event, e1))
                
                if len(linkedEvents) and len(targetEntityList): # and len(allTimex) < 4:
                    (linkedEntities_pred, pred) = argmaxEventEntity(doc, linkedEvents, targetEntityList, w, local_feat_dict, global_feat_dict)
                                            
                    if not tuple(linkedEntities) == linkedEntities_pred:
                        w = w + (getPHI(doc, linkedEvents, linkedEntities, local_feat_dict, global_feat_dict) - getPHI(doc, linkedEvents, linkedEntities_pred, local_feat_dict, global_feat_dict))
                        #wa = wa + c * (getPHI(doc, linkedEvents, linkedTimex, local_feat_dict, global_feat_dict) - getPHI(doc, linkedEvents, linkedTimex_pred, local_feat_dict, global_feat_dict))
                    wa = wa + w
                    c += 1
    return wa/c # w - wa/c

def getPHI(doc, listEvents, listTimex, local_feat_dict, global_feat_dict):
    PHI = np.zeros(500) # TBD: zise
    
    # local features
    for event, timex in zip(listEvents, listTimex):
        PHI += local_feat_dict[(event, timex)]
        
    # global features
    PHI2 = np.zeros(10)
    for ind in range(1, len(listEvents)):
        prev_event = listEvents[ind-1]
        prev_timex = listTimex[ind-1]
        event = listEvents[ind]
        timex = listTimex[ind]
        PHI2 += global_feat_dict[((prev_event, prev_timex),(event, timex))]
        
    return np.append(PHI, PHI2)

def structuredPrediction(w, doc, listEvents, targetEntityList, syntactic_features):
    '''Given the weights from the structured perceptron predict the TIMEX3 associated with the Event'''
    # NB!!!! Are we assuming that the events are ordered? Does it matter?
            
    # precompute features
    local_feat_dict = dict()
    for event in listEvents:
        for entity in targetEntityList:
            local_feat_dict[(event, entity)] = getLinkFeatures(doc, event, entity, syntactic_features)
            
    global_feat_dict = dict()
    for e in range(1, len(listEvents)):
        prev_event = listEvents[e-1]
        event = listEvents[e]
        for e0 in targetEntityList:
            for e1 in targetEntityList:
                global_feat_dict[((prev_event, e0),(event, e1))] = getGlobalFeatures(doc, (prev_event, e0), (event, e1))
    
    #(best_timex, predicted_prob) = argmaxEventTIMEX(doc, event, timexList, w, syntactic_features)
    (best_seq, best_pred) = argmaxEventEntity(doc, listEvents, targetEntityList, w, local_feat_dict, global_feat_dict)

    return best_seq

def linkEventEntitySP(w, doc, targetEntityList, syntactic_features):
    res = dict()
    for targetEntity in targetEntityList:
        res[targetEntity] = []
    
    if len(targetEntityList):
        listEvents = doc.Markables.EVENT_MENTION
            
        predictedEntity_list = structuredPrediction(w, doc, listEvents, targetEntityList, syntactic_features)
        
        #print len(listEvents), len(predictedEntity_list)
        #print listEvents, predictedEntity_list
        
        for i in range(len(predictedEntity_list)):
            res[predictedEntity_list[i]].append(listEvents[i].m_id)
        
    return res

'''
def linkEventEntityML(clf, doc, targetEntityList, syntactic_features):
    # prep dictionary
    res = dict()
    for targetEntity in targetEntityList:
        res[targetEntity] = []
        
    # loop over events and predict for each event
    for event in doc.Markables.EVENT_MENTION:
        predictedEntityList = predictEventEntityLink(clf, doc, event, targetEntityList, syntactic_features)
        for predictedEntity in predictedEntityList:
            if targetEntityList.count(predictedEntity): # check if the predicted entity is not 'unknown'
                res[predictedEntity].append(event.m_id)
    return res
'''

def argmaxEventEntity(doc, linkedEvents, targetEntityList, w, local_feat_dict, global_feat_dict):
    '''Find the argmax'''
    ew = w[0:500]
    tw = w[500:510]
    hmm = hmmClass(targetEntityList, global_feat_dict, local_feat_dict, tw, ew)
        
    thisViterbi = Viterbi(hmm, linkedEvents)
    best_seq = thisViterbi.return_max()
    
    return (best_seq, 0)

class hmmClass(object):
    def __init__(self,labels, tProb, eProb, tw, ew):
        self.labels = labels
        self.tProb=tProb
        self.eProb=eProb
        self.tw=tw
        self.ew=ew

class Viterbi:
    trell = []
    def __init__(self, hmm, words):
        self.trell = []
        temp = {}
        for label in hmm.labels:
           temp[label] = [0,None]
        for word in words:
            self.trell.append([word,copy.deepcopy(temp)])
        self.fill_in(hmm)

    def fill_in(self,hmm):
        for i in range(len(self.trell)):
            for token in self.trell[i][1]:
                word = self.trell[i][0]
                if i == 0:
                    self.trell[i][1][token][0] = np.dot(hmm.eProb[(word, token)], hmm.ew)
                else:
                    max = None
                    guess = None
                    c = None
                    prev_word = self.trell[i-1][0]
                    for k in self.trell[i-1][1]:
                        c = self.trell[i-1][1][k][0] + np.dot(hmm.tProb[((prev_word, k), (word, token))], hmm.tw)
                        if max == None or c > max:
                            max = c
                            guess = k
                    max += np.dot(hmm.eProb[(word, token)], hmm.ew)
                    self.trell[i][1][token][0] = max
                    self.trell[i][1][token][1] = guess

    def return_max(self):
        tokens = []
        token = None
        for i in range(len(self.trell)-1,-1,-1):
            if token == None:
                max = None
                guess = None
                for k in self.trell[i][1]:
                    if max == None or self.trell[i][1][k][0] > max:
                        max = self.trell[i][1][k][0]
                        token = self.trell[i][1][k][1]
                        guess = k
                tokens.append(guess)
            else:
                tokens.append(token)
                token = self.trell[i][1][token][1]
        tokens.reverse()
        return tokens

def getGlobalFeatures(doc, t0, t1):
    '''t0 and t1 are adjacent hidden variables in a HMM representing a (event, timex) tuple.'''
    features = np.zeros(10)
    stemmer = porter.PorterStemmer()
    
    (event0, entity0) = t0
    (event1, entity1) = t1
    
    event_t_id = event0.get_token_anchor()[0].t_id
    event_sentence0 = utils.getToken(doc, event_t_id).sentence
    
    event_t_id = event1.get_token_anchor()[0].t_id
    event_sentence1 = utils.getToken(doc, event_t_id).sentence
    
    str_event0 = utils.getEventTextFull(doc, event0)
    str_event1 = utils.getEventTextFull(doc, event1)
    
    stem0 = stemmer.stem(str_event0.split('_')[0])
    stem1 = stemmer.stem(str_event1.split('_')[0])

    if entity0 == entity1:
        features[0] = 1
    ind = 1

    if not entity0 == entity1:
        features[ind] = 1
    ind += 1
    
    # event string
    if entity0 == entity1 and str_event0 == str_event1:
        features[ind] = 1
    ind += 1

    # event stem
    if entity0 == entity1 and stem0 == stem1:
        features[ind] = 1
    ind += 1

    # sentence
    if entity0 == entity1 and event_sentence0 == event_sentence1:
        features[ind] = 1
    ind += 1

    # talking words
    talking_words = ['said','presented','explained','proposed','stated','thanked','refused','described','pointed','responded','anticipated','concluded', 'called', 'praised']
    # timex and event string type
    if entity0 == entity1 and talking_words.count(str_event0) and talking_words.count(str_event1):
        features[ind] = 1
    ind += 1

    return features




