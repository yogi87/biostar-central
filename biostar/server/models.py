"""
Model definitions.

Note: some models are denormalized by design, this greatly simplifies (and speeds up) 
the queries necessary to fetch a certain entry.

"""
from django.db import models
from django.contrib.auth.models import User

from datetime import datetime
from biostar.server import html
import markdown

class UserProfile( models.Model ):
    """
    Stores user options

    >>> user, flag = User.objects.get_or_create(first_name='Jane', last_name='Doe', username='jane', email='jane')
    >>> prof = user.get_profile()
    >>> prof.json = dict( message='Hello world' )
    >>> prof.save()
    """
    user  = models.OneToOneField(User, unique=True, related_name='profile')
    score = models.IntegerField(default=0, blank=True)
    bronze_badges = models.IntegerField(default=0)
    silver_badges = models.IntegerField(default=0)
    gold_badges = models.IntegerField(default=0)
    json  = models.TextField(default="", null=True)
    last_visited = models.DateTimeField(auto_now=True)
    creation_date = models.DateTimeField(auto_now_add=True)

class Tag(models.Model):
    name = models.TextField(max_length=50)
    count = models.IntegerField(default=0)

class Post(models.Model):
    """
    A posting is the basic content generated by a user
    
    >>> user, flag = User.objects.get_or_create(first_name='Jane', last_name='Doe', username='jane', email='jane')
    >>> post = Post.objects.create(author=user)
    >>> content ='*A*'
    >>> post.set(content)
    >>> post.html
    u'<p><em>A</em></p>'
    """
    author = models.ForeignKey(User)
    
    content = models.TextField() # this is the user inpu
    html    = models.TextField() # this is the sanitized HTML for display
    tag_string = models.CharField(max_length=200) # The tag string is the canonical form of the post's tags
    tag_set = models.ManyToManyField(Tag) # The tag set is built from the tag string and used only for fast filtering
    views = models.IntegerField(default=0, blank=True)
    score = models.IntegerField(default=0, blank=True)
    comment_count = models.IntegerField(default=0)
    creation_date = models.DateTimeField()
    lastedit_date = models.DateTimeField(auto_now=True)
    lastedit_user = models.ForeignKey(User, related_name='editor')

    def set(self, content, safe_mode='remove'):
        "Sets the html field by sanitizing the content"
        
        # transform the content to UNIX style line endings
        content = "\n".join( content.splitlines() )
        
        self.content = content
        self.html = markdown.markdown(self.content, safe_mode=safe_mode)
        #self.html = html.sanitize(content)
        self.save()

        # this is for debugging
        if 0:
            print '**** content ****' 
            print repr(self.content)
            print '---- html ----'
            print repr(self.html)

    def authorize(self, request, strict=False):
        "Verfifies access by a request object. Strict mode fails immediately."
        cond1 = request.user == self.author
        cond2 = request.user.is_staff
        valid = cond1 or cond2
        if strict and not valid:
            raise Exception("Access Denied!")
        return valid

    def get_vote(self, user, vote_type):
        if user.is_anonymous():
            return None
        try:
            return self.votes.get(author=user, type=vote_type)
        except Vote.DoesNotExist:
            return None
        
    def add_vote(self, user, vote_type):
        vote = Vote(author=user, type=vote_type, post=self)
        vote.save()
        return vote
        
    def remove_vote(self, user, vote_type):
        ''' Removes a vote from a user of a certain type if it exists
        Returns True if removed, False if it didn't exist'''
        vote = self.get_vote(user, vote_type)
        if vote:
            vote.delete()
            return True
        return False
    
    def get_comments(self):
        return self.comments.select_related('post','post__author').all()
        
    def set_tags(self, tag_string):
        ''' Sets the post's tags to a space-separated string of tags '''
        self.tag_string = tag_string
        self.save()
        self.tag_set.clear()
        tags = []
        for tag_name in tag_string.split(' '):
            try:
                tags.append(Tag.objects.get(name=tag_name))
            except Tag.DoesNotExist:
                tag = Tag(name=tag_name)
                tag.save()
                tags.append(tag)
        self.tag_set.add(*tags)
        
        
    def get_tags(self):
        ''' Returns the post's tags as a list of strings '''
        return self.tag_string.split(' ')
        

class Question(models.Model):
    """
    A Question is Post with title and tags
    
    >>> user, flag = User.objects.get_or_create(first_name='Jane', last_name='Doe', username='jane', email='jane')
    >>> post = Post.objects.create(author=user)
    >>> post.set('ABC')
    >>> question, flag = Question.objects.get_or_create(post=post, title='Test questions')
    >>> question.post.set_tags("snp codon microarray")
    """
    title   = models.TextField()
    answer_count = models.IntegerField(default=0, blank=True)
    post = models.OneToOneField(Post, related_name='question')
    lastedit_date = models.DateTimeField(auto_now=True)
    answer_accepted = models.BooleanField(default=False)

    def authorize(self, request, strict=False):
        return self.post.authorize(request, strict=strict)

class Answer(models.Model):
    question = models.ForeignKey(Question, related_name='answers')
    post = models.OneToOneField(Post, related_name='answer')
    lastedit_date = models.DateTimeField(auto_now=True)
    accepted = models.BooleanField(default=False)
    
    def author(self):
        return self.post.author

    def authorize(self, request, strict=False):
        return self.post.authorize(request, strict=strict)
        
    def apply(self, dir=1):
        self.question.answer_count += dir
        self.question.save()
        

class Comment(models.Model):
    parent = models.ForeignKey(Post, related_name='comments')
    post = models.ForeignKey(Post)
    lastedit_date = models.DateTimeField(auto_now=True)
    
    def apply(self, dir=1):
        ''' Updates the parent post's comment count '''
        self.parent.comment_count += dir
        self.parent.save()

VOTE_UP, VOTE_DOWN, VOTE_ACCEPT = 0, 1, 2

VOTE_TYPES = ((VOTE_UP, 'Upvote'), (VOTE_DOWN, 'Downvote'), (VOTE_ACCEPT, 'Accept'))

OPPOSING_VOTES = {VOTE_UP:VOTE_DOWN, VOTE_DOWN:VOTE_UP} # Mappings of mutually exclusive votes

# post score changes
POST_SCORE = { VOTE_UP:1, VOTE_DOWN:-1 }

# user reputation changes
USER_REP   = { VOTE_UP:10, VOTE_DOWN:-2, VOTE_ACCEPT:15 }
VOTER_REP = { VOTE_DOWN: -1, VOTE_ACCEPT:2 }

class Vote(models.Model):
    """
    >>> user, flag = User.objects.get_or_create(first_name='Jane', last_name='Doe', username='jane', email='jane')
    >>> post = Post.objects.create(author=user)
    >>> post.set('ABC')
    >>> vote = Vote(author=user, post=post, type=VOTE_UP)
    >>> vote.score()
    1
    """
    author = models.ForeignKey(User)
    post = models.ForeignKey(Post, related_name='votes')
    type = models.IntegerField(choices=VOTE_TYPES)
    
    def score(self):
        return POST_SCORE.get(self.type, 0)
    
    def reputation(self):
        return USER_REP.get(self.type, 0)
        
    def voter_reputation(self):
        return VOTER_REP.get(self.type, 0)
    
    def apply(self, dir=1):
        "Applies the score and reputation changes. Direction can be set to -1 to undo (ie delete vote)"
        if self.reputation():
            prof = self.post.author.get_profile()
            prof.score += dir * self.reputation()
            prof.save()
        
        if self.voter_reputation():
            prof = self.author.get_profile()
            prof.score += dir * self.voter_reputation()
            prof.save()

        if self.score():
            self.post.score += dir * self.score()
            self.post.save()
            
        if self.type == VOTE_ACCEPT:
            answer = self.post.answer
            question = answer.question
            if dir == 1:
                answer.accepted = True
                question.answer_accepted = True
            else:
                answer.accepted = False
                question.answer_accepted = False
            answer.save()
            question.save()
            
BADGE_BRONZE = 0
BADGE_SILVER = 1
BADGE_GOLD = 2

BADGE_TYPES = ((BADGE_BRONZE, 'bronze'), (BADGE_SILVER, 'silver'), (BADGE_GOLD, 'gold'))
            
class Badge(models.Model):
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=200)
    type = models.IntegerField(choices=BADGE_TYPES)
    unique = models.BooleanField() # Unique badges may be earned only once
    secret = models.BooleanField() # Secret badges are not listed on the badge list
    count = models.IntegerField(default=0) # Total number of times awarded
    
class Award(models.Model):
    ''' A badge being awarded to a user.Cannot be ManyToManyField
    because some may be earned multiple times'''
    badge = models.ForeignKey(Badge)
    user = models.ForeignKey(User)
    date = models.DateTimeField()
    
    def apply(self, dir=1):
        type = self.badge.type
        prof = self.user.get_profile()
        if type == BADGE_BRONZE:
            prof.bronze_badges += dir
        if type == BADGE_SILVER:
            prof.silver_badges += dir
        if type == BADGE_GOLD:
            prof.gold_badges += dir
        prof.save()
        self.badge.count += dir
        self.badge.save()
    


#
# Adding data model related signals
#
from django.db.models import signals


# Many models have apply() methods that need to be called when they are created
# and called with dir=-1 when deleted to update something.
    
MODELS_WITH_APPLY = [Vote, Award, Comment, Answer]
    
def apply_instance(sender, instance, created, raw, *args, **kwargs):
    "Applies changes from an instance with an apply() method"
    if created and not raw: # Raw is true when importing from fixtures, in which case votes are already applied
        instance.apply()

def unapply_instance(sender, instance,  *args, **kwargs):
    "Unapplies an instance when it is deleted"
    instance.apply(-1)
    
for model in MODELS_WITH_APPLY:
    signals.post_save.connect(apply_instance, sender=model)
    signals.post_delete.connect(apply_instance, sender=model)
    
# Other objects have more unique signals

def create_profile(sender, instance, created, *args, **kwargs):
    "Post save hook for creating user profiles"
    if created:
        UserProfile.objects.create( user=instance )

def create_post(sender, instance, *args, **kwargs):
    "Pre save post information"
    if not hasattr(instance, 'lastedit_user'):
        instance.lastedit_user = instance.author
    if not instance.creation_date:
        instance.creation_date = datetime.now()

    
def create_award(sender, instance, *args, **kwargs):
    if not instance.date:
        instance.date = datetime.now()
        
             
def tags_changed(sender, instance, action, pk_set, *args, **kwargs):
    if action == 'post_add':
        for pk in pk_set:
            tag = Tag.objects.get(pk=pk)
            tag.count += 1
            tag.save()
    if action == 'post_delete':
        for pk in pk_set:
            tag = Tag.objects.get(pk=pk)
            tag.count -= 1
            tag.save()
    if action == 'pre_clear': # Must be pre so we know what was cleared
        for tag in instance.tag_set.all():
            tag.count -= 1
            tag.save()
        
    

signals.post_save.connect( create_profile, sender=User )
signals.pre_save.connect( create_post, sender=Post )
signals.pre_save.connect(create_award, sender=Award)

signals.m2m_changed.connect( tags_changed, sender=Post.tag_set.through)




